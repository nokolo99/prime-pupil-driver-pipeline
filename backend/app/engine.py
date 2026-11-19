"""Stage engine: the follow-up loop.

tick() runs every 30 seconds (and immediately after the demo clock moves). For every step
that is waiting on the candidate, it checks the follow-up schedule and sends whatever is due.
It never advances or rejects anyone; at the end of the schedule it hands off to a recruiter.

In production this same function would run on a scheduler / worker queue instead of in the web process.
"""

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from .config import DEFAULT_FOLLOW_UP, FOLLOW_UP_SCHEDULE, GIVE_UP_AFTER_DAYS, LOCAL_TZ, QUIET_HOURS
from .conversation import create_task, log_event, send, template
from .models import Actor, Candidate, CandidateStatus, Sender, Step, StepStatus, Task, TaskStatus, now

log = logging.getLogger(__name__)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def in_quiet_hours(t: datetime) -> bool:
    hour = t.astimezone(ZoneInfo(LOCAL_TZ)).hour
    start, end = QUIET_HOURS
    return hour >= start or hour < end


def last_activity(c: Candidate, step: Step) -> datetime:
    """Clock for follow-ups: restarts whenever the candidate replies."""
    times = [t for t in (step.started_at, c.last_reply_at) if t]
    return max(_aware(t) for t in times)


def tick(s: Session) -> int:
    """Returns how many actions were taken."""
    t = now()
    actions = 0
    steps = s.exec(select(Step).where(Step.status == StepStatus.waiting_on_candidate)).all()
    for step in steps:
        c = s.get(Candidate, step.candidate_id)
        if c.opted_out or c.status in (CandidateStatus.needs_review, CandidateStatus.rejected,
                                       CandidateStatus.dropped, CandidateStatus.hired):
            continue
        schedule = FOLLOW_UP_SCHEDULE.get(step.stage.value, DEFAULT_FOLLOW_UP)
        idle_days = (t - last_activity(c, step)).total_seconds() / 86400

        # End of the line: stop reminders, hand to a recruiter (once).
        if idle_days >= GIVE_UP_AFTER_DAYS:
            already = s.exec(select(Task).where(Task.candidate_id == c.id, Task.type == "candidate_unresponsive",
                                                Task.status == TaskStatus.open)).first()
            if not already:
                create_task(s, c, "candidate_unresponsive",
                            f"No response for {GIVE_UP_AFTER_DAYS} days at {step.stage.value.replace('_', ' ')}; "
                            f"{step.nudge_count} reminders sent", priority=2)
                actions += 1
            continue

        # Next scheduled follow-up (nudge_count = how many already sent since last activity).
        if step.nudge_count >= len(schedule):
            continue
        due_day, kind = schedule[step.nudge_count]
        if idle_days < due_day or in_quiet_hours(t):
            continue

        n = step.nudge_count + 1
        if kind == "call":
            # Voice arrives in increment 5. Until then, log the intended call and text instead.
            log_event(s, c, "ai_call_placeholder", Actor.system, attempt=n, day=due_day)
            body, en = template("call_fallback", c.preferred_language, first_name=c.first_name)
        else:
            level = 1 if due_day <= 2 else 2 if due_day <= 10 else 3
            body, en = template(f"reminder_{level}", c.preferred_language, first_name=c.first_name)
        send(s, c, body, en, Sender.system)
        log_event(s, c, "nudge_sent", Actor.system, attempt=n, day=due_day, kind=kind, stage=step.stage.value)
        step.nudge_count, step.last_nudged_at = n, t
        actions += 1

    s.commit()
    return actions


def reset_follow_up(step: Step) -> None:
    """Called when the candidate replies or a recruiter extends: restart the schedule."""
    step.nudge_count = 0
    step.last_nudged_at = None

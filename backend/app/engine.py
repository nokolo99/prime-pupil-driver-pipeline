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

from . import telephony
from datetime import timedelta

from .config import (DEFAULT_FOLLOW_UP, FOLLOW_UP_SCHEDULE, GIVE_UP_AFTER_DAYS, LOCAL_TZ, QUIET_HOURS,
                     RESULTS_OVERDUE_DAYS)
from .conversation import create_task, log_event, send, template
from .models import (Actor, BackgroundCheck, Candidate, CandidateStatus, Clinic, DrugTest, Offer, Sender, SkillsTest,
                     Stage, Step, StepStatus, Task, TaskStatus, Training, now)

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


def _reminder(s: Session, c: Candidate, step: Step, due_day: int) -> tuple[str, str]:
    """Stage-specific reminder text (includes the link the candidate needs)."""
    if step.stage == Stage.background_check:
        bc = s.get(BackgroundCheck, step.id)
        return template("bg_reminder", c.preferred_language, first_name=c.first_name, link=bc.form_link)
    if step.stage == Stage.drug_test:
        dt = s.get(DrugTest, step.id)
        return template("drug_reminder", c.preferred_language, first_name=c.first_name, link=dt.booking_link)
    if step.stage == Stage.cdl_permit:
        from .config import DMV_PERMIT_LINK
        return template("permit_reminder", c.preferred_language, first_name=c.first_name, link=DMV_PERMIT_LINK)
    if step.stage == Stage.skills_test:
        return template("skills_reminder", c.preferred_language, first_name=c.first_name, link=s.get(SkillsTest, step.id).test_link)
    if step.stage == Stage.offer:
        return template("offer_reminder", c.preferred_language, first_name=c.first_name, link=s.get(Offer, step.id).sign_link)
    level = 1 if due_day <= 2 else 2 if due_day <= 10 else 3
    return template(f"reminder_{level}", c.preferred_language, first_name=c.first_name)


def _training_reminders(s: Session, t) -> int:
    from .stages import fmt_when
    actions = 0
    for tr in s.exec(select(Training).where(Training.completed_at == None)).all():  # noqa: E711
        step = s.get(Step, tr.step_id)
        c = s.get(Candidate, step.candidate_id)
        if c.opted_out or c.stage != Stage.training or in_quiet_hours(t):
            continue
        start = _aware(tr.cohort_start)
        lt, ls = t.astimezone(ZoneInfo(LOCAL_TZ)), start.astimezone(ZoneInfo(LOCAL_TZ))
        if not tr.reminded_morning_of and lt.date() == ls.date() and lt < ls:
            body, en = template("training_morning_of", c.preferred_language, time=ls.strftime("%-I:%M %p"), link=tr.session_link)
            tr.reminded_morning_of = tr.reminded_day_before = True
        elif not tr.reminded_day_before and ls.date() - lt.date() == timedelta(days=1):
            body, en = template("training_day_before", c.preferred_language, when=fmt_when(start), link=tr.session_link)
            tr.reminded_day_before = True
        else:
            continue
        send(s, c, body, en, Sender.system)
        log_event(s, c, "training_reminder", Actor.system)
        actions += 1
    return actions


def _appointments(s: Session, t) -> int:
    """Drug test appointment reminders (day before, morning of) and missed-appointment detection."""
    from .stages import drug_event, fmt_when
    actions = 0
    rows = s.exec(select(DrugTest).where(DrugTest.appointment_at != None, DrugTest.collected_at == None)).all()  # noqa: E711
    for dt in rows:
        step = s.get(Step, dt.step_id)
        c = s.get(Candidate, step.candidate_id)
        if c.opted_out or step.status != StepStatus.waiting_on_candidate:
            continue
        appt = _aware(dt.appointment_at)
        local_t, local_appt = t.astimezone(ZoneInfo(LOCAL_TZ)), appt.astimezone(ZoneInfo(LOCAL_TZ))
        clinic = s.get(Clinic, dt.clinic_id)
        args = dict(clinic=clinic.name, when=fmt_when(appt), link=dt.booking_link)
        if t > appt + timedelta(hours=24):  # no collection a day after: treat as missed, offer to rebook
            drug_event(s, dt.vendor_case_id, "no_show")
            actions += 1
        elif not dt.reminded_morning_of and local_t.date() == local_appt.date() and local_t < local_appt and not in_quiet_hours(t):
            body, en = template("drug_morning_of", c.preferred_language, **args)
            send(s, c, body, en, Sender.system)
            log_event(s, c, "appointment_reminder", Actor.system, kind="morning_of")
            dt.reminded_morning_of = dt.reminded_day_before = True
            actions += 1
        elif not dt.reminded_day_before and local_appt.date() - local_t.date() == timedelta(days=1) and not in_quiet_hours(t):
            body, en = template("drug_day_before", c.preferred_language, **args)
            send(s, c, body, en, Sender.system)
            log_event(s, c, "appointment_reminder", Actor.system, kind="day_before")
            dt.reminded_day_before = True
            actions += 1
    return actions


def _overdue(s: Session, t) -> int:
    """Vendor results taking too long: FYI flag for the recruiter (no action required)."""
    actions = 0
    for step in s.exec(select(Step).where(Step.status == StepStatus.waiting_on_vendor, Step.flag_note == None)).all():  # noqa: E711
        if step.stage == Stage.background_check:
            since = s.get(BackgroundCheck, step.id).form_completed_at
        elif step.stage == Stage.drug_test:
            since = s.get(DrugTest, step.id).collected_at
        else:
            continue
        limit = RESULTS_OVERDUE_DAYS.get(step.stage.value)
        if since and limit and t - _aware(since) > timedelta(days=limit):
            days = (t - _aware(since)).days
            step.flag_note = f"Results overdue ({days} days with vendor)"
            log_event(s, s.get(Candidate, step.candidate_id), "results_overdue", Actor.system, stage=step.stage.value, days=days)
            actions += 1
    return actions


def tick(s: Session) -> int:
    """Returns how many actions were taken."""
    t = now()
    actions = _appointments(s, t) + _overdue(s, t) + _training_reminders(s, t)
    steps = s.exec(select(Step).where(Step.status == StepStatus.waiting_on_candidate)).all()
    for step in steps:
        c = s.get(Candidate, step.candidate_id)
        if step.stage != c.stage:
            continue
        if step.stage == Stage.drug_test:
            dt = s.get(DrugTest, step.id)
            if dt and dt.appointment_at:
                continue  # booked: appointment reminders handle it
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
        if kind == "call" and telephony.voice_ready():
            try:
                sid = telephony.place_call(c.phone, c.id, "follow_up")
                log_event(s, c, "ai_call_placed", Actor.system, attempt=n, day=due_day, call_sid=sid)
                log_event(s, c, "nudge_sent", Actor.system, attempt=n, day=due_day, kind="call", stage=step.stage.value)
                step.nudge_count, step.last_nudged_at = n, t
                actions += 1
                continue
            except Exception as e:
                log.exception("call failed")
                log_event(s, c, "ai_call_failed", Actor.system, error=str(e)[:200])
            body, en = template("call_fallback", c.preferred_language, first_name=c.first_name)
        elif kind == "call":
            # Voice not configured: log the intended call and text instead.
            log_event(s, c, "ai_call_placeholder", Actor.system, attempt=n, day=due_day)
            body, en = template("call_fallback", c.preferred_language, first_name=c.first_name)
        else:
            body, en = _reminder(s, c, step, due_day)
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

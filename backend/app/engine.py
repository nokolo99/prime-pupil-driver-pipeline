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

from . import settings
from .config import LOCAL_TZ
from .conversation import create_task, log_event, send, template
from .models import (Actor, BackgroundCheck, Candidate, CandidateStatus, Clinic, DrugTest, Offer, Sender, SkillsTest,
                     Stage, Step, StepStatus, Task, TaskStatus, Training, now)

log = logging.getLogger(__name__)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def in_quiet_hours(t: datetime) -> bool:
    hour = t.astimezone(ZoneInfo(LOCAL_TZ)).hour
    start, end = settings.quiet_hours()
    return hour >= start or hour < end


def last_activity(c: Candidate, step: Step) -> datetime:
    """Clock for follow-ups: restarts whenever the candidate replies."""
    times = [t for t in (step.started_at, c.last_reply_at) if t]
    return max(_aware(t) for t in times)


def _reminder(s: Session, c: Candidate, step: Step, attempt: int) -> tuple[str, str]:
    """Stage-specific reminder (with the link the candidate needs), rotating through approved variations."""
    from .config import DMV_PERMIT_LINK, reminder_key
    from .models import PermitCheck
    lang, name = c.preferred_language, c.first_name
    stage = step.stage.value
    if stage == "cdl_permit":
        pc = s.get(PermitCheck, step.id)
        if pc and pc.photo_requested_at:  # offer is waiting on the permit photo
            return template("permit_photo_request", lang, first_name=name)
        return template(reminder_key(stage, attempt), lang, first_name=name, link=DMV_PERMIT_LINK)
    link = None
    if stage == "background_check":
        link = s.get(BackgroundCheck, step.id).form_link
    elif stage == "drug_test":
        link = s.get(DrugTest, step.id).booking_link
    elif stage == "skills_test":
        link = s.get(SkillsTest, step.id).test_link
    elif stage == "offer":
        o = s.get(Offer, step.id)
        if not o:  # offer not sent yet (waiting on permit photo)
            return template("permit_photo_request", lang, first_name=name)
        link = o.sign_link
    elif stage != "screening":
        return template("reminder_2", lang, first_name=name)
    return template(reminder_key(stage, attempt), lang, first_name=name, **({"link": link} if link else {}))


def _training_reminders(s: Session, t) -> int:
    from .stages import fmt_when
    actions = 0
    for tr in s.exec(select(Training).where(Training.completed_at == None)).all():  # noqa: E711
        step = s.get(Step, tr.step_id)
        c = s.get(Candidate, step.candidate_id) if step else None
        if not c:
            continue
        if c.opted_out or c.stage != Stage.training or in_quiet_hours(t):
            continue
        start = _aware(tr.cohort_start)
        lt, ls = t.astimezone(ZoneInfo(LOCAL_TZ)), start.astimezone(ZoneInfo(LOCAL_TZ))
        if not tr.reminded_morning_of and lt.date() == ls.date() and lt < ls:
            body, en = template("training_morning_of", c.preferred_language, time=ls.strftime("%-I:%M %p"), link=tr.session_link)
            tr.reminded_morning_of = tr.reminded_day_before = True
        elif not tr.reminded_day_before and ls.date() - lt.date() == timedelta(days=1):
            body, en = template("training_day_before", c.preferred_language, when=fmt_when(start, c.preferred_language), link=tr.session_link)
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
        c = s.get(Candidate, step.candidate_id) if step else None
        if not c:
            continue
        if c.opted_out or step.status != StepStatus.waiting_on_candidate:
            continue
        appt = _aware(dt.appointment_at)
        local_t, local_appt = t.astimezone(ZoneInfo(LOCAL_TZ)), appt.astimezone(ZoneInfo(LOCAL_TZ))
        clinic = s.get(Clinic, dt.clinic_id) if dt.clinic_id else None
        any_clinic = "una clínica de la red" if c.preferred_language == "es" else "any clinic in the network"
        args = dict(clinic=clinic.name if clinic else any_clinic, when=fmt_when(appt, c.preferred_language), link=dt.booking_link)
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
        limit = settings.results_overdue_days().get(step.stage.value)
        if since and limit and t - _aware(since) > timedelta(days=limit):
            days = (t - _aware(since)).days
            step.flag_note = f"Results overdue ({days} days with vendor)"
            log_event(s, s.get(Candidate, step.candidate_id), "results_overdue", Actor.system, stage=step.stage.value, days=days)
            actions += 1
    return actions


def _watch_training_sheet(s: Session) -> int:
    """Watch the trainer's shared spreadsheet: a row marked Completed moves the candidate on automatically.
    (Prod: read their Google Sheet / Excel through its API on this same schedule.)"""
    from .models import TrainingSheetRow
    from .stages import training_completed
    actions = 0
    for row in s.exec(select(TrainingSheetRow).where(TrainingSheetRow.completed == True, TrainingSheetRow.processed == False)).all():  # noqa: E712
        c = s.get(Candidate, row.candidate_id)
        row.processed = True
        if c and c.stage == Stage.training:
            log_event(s, c, "training_sheet_completed_detected", Actor.system, cohort=row.cohort)
            training_completed(s, c)
            actions += 1
    return actions


def tick(s: Session) -> int:
    """Returns how many actions were taken."""
    t = now()
    actions = 0
    for part in (_appointments, _overdue, _training_reminders):  # one bad record must never stop the whole tick
        try:
            actions += part(s, t)
        except Exception:
            log.exception("engine: %s failed", part.__name__)
            s.rollback()
    try:
        actions += _watch_training_sheet(s)
    except Exception:
        log.exception("engine: training sheet watch failed")
        s.rollback()
    from .workday import dispatch_outbox
    dispatch_outbox()  # retry any Workday writes that failed
    steps = s.exec(select(Step).where(Step.status == StepStatus.waiting_on_candidate)).all()
    # Safety net: only the newest step per (candidate, stage) gets reminders.
    newest = {}
    for st in s.exec(select(Step)).all():
        k = (st.candidate_id, st.stage)
        if k not in newest or st.id > newest[k]:
            newest[k] = st.id
    for step in steps:
        if newest.get((step.candidate_id, step.stage)) != step.id:
            continue
        c = s.get(Candidate, step.candidate_id)
        if not c:
            continue
        if step.stage != c.stage and step.stage != Stage.cdl_permit:
            continue  # the permit is a parallel track, so it's nudged whatever stage they're in
        if step.stage == Stage.drug_test:
            dt = s.get(DrugTest, step.id)
            if dt and dt.appointment_at:
                continue  # booked: appointment reminders handle it
        if c.opted_out or c.status in (CandidateStatus.needs_review, CandidateStatus.rejected,
                                       CandidateStatus.dropped, CandidateStatus.hired):
            continue
        schedule = settings.follow_up_schedule(step.stage.value)
        give_up = settings.give_up_after_days()
        idle_days = (t - last_activity(c, step)).total_seconds() / 86400

        # End of the line: stop reminders, hand to a recruiter (once).
        if idle_days >= give_up:
            already = s.exec(select(Task).where(Task.candidate_id == c.id, Task.type == "candidate_unresponsive",
                                                Task.status == TaskStatus.open)).first()
            if not already:
                create_task(s, c, "candidate_unresponsive",
                            f"No response for {give_up} days at {step.stage.value.replace('_', ' ')}; "
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
        text_n = sum(1 for _, k in schedule[:n] if k == "sms") or 1  # rotate versions by texts only (calls don't count)
        if kind == "call" and not settings.ai_calls_enabled():
            kind = "sms"  # AI calls turned off in Settings: send a text instead
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
            body, en = _reminder(s, c, step, text_n + 1)  # couldn't call: send the next reminder version (with link)
        elif kind == "call":
            # Voice not configured: log the intended call and send the stage's reminder instead.
            log_event(s, c, "ai_call_placeholder", Actor.system, attempt=n, day=due_day)
            body, en = _reminder(s, c, step, text_n + 1)
        else:
            body, en = _reminder(s, c, step, text_n)
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

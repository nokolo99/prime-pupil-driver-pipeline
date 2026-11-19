"""Stage transitions for background check and drug test.

Every function here is called by code (vendor events, recruiter actions, the engine), never by
Claude. Each one updates the step, tells the candidate what happens next, and logs an event.
"""

from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from . import vendors, workday
from .config import LOCAL_TZ
from .conversation import create_task, log_event, send, template
from .models import (Actor, BackgroundCheck, Candidate, CandidateStatus, Clinic, DrugTest, Sender, Stage,
                     Step, StepResult, StepStatus, now)

NEXT_STAGE = {Stage.screening: Stage.background_check, Stage.background_check: Stage.drug_test,
              Stage.drug_test: Stage.cdl_permit}


def current_step(s: Session, c: Candidate) -> Step:
    return s.exec(select(Step).where(Step.candidate_id == c.id, Step.stage == c.stage)
                  .order_by(Step.id.desc())).first()


def fmt_when(dt: datetime) -> str:
    dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo(LOCAL_TZ)).strftime("%a %b %-d, %-I:%M %p")


def advance(s: Session, c: Candidate, to: Stage) -> Step:
    """Move to the next stage and run its entry actions."""
    log_event(s, c, "stage_changed", Actor.system, **{"from": c.stage.value, "to": to.value})
    c.stage, c.stage_entered_at = to, now()
    step = Step(candidate_id=c.id, stage=to, status=StepStatus.not_started, started_at=now())
    s.add(step)
    s.flush()
    workday.push_stage(s, c, to.value)
    if to == Stage.background_check:
        _enter_background_check(s, c, step)
    elif to == Stage.drug_test:
        _enter_drug_test(s, c, step)
    else:
        c.status = CandidateStatus.waiting_on_candidate  # later stages are Tier 2
    return step


# ---------- Background check ----------

def _enter_background_check(s: Session, c: Candidate, step: Step) -> None:
    order = vendors.order_background_check(c.id)
    s.add(BackgroundCheck(step_id=step.id, vendor_order_id=order["order_id"], form_link=order["form_link"],
                          report_status="form_pending"))
    step.status = StepStatus.waiting_on_candidate
    c.status = CandidateStatus.waiting_on_candidate
    log_event(s, c, "bg_ordered", Actor.system, order_id=order["order_id"])
    body, en = template("bg_start", c.preferred_language, link=order["form_link"])
    send(s, c, body, en, Sender.system)


def bg_form_completed(s: Session, order_id: str) -> Optional[Candidate]:
    bc = s.exec(select(BackgroundCheck).where(BackgroundCheck.vendor_order_id == order_id)).first()
    if not bc or bc.form_completed_at:
        return None
    step = s.get(Step, bc.step_id)
    c = s.get(Candidate, step.candidate_id)
    bc.form_completed_at, bc.report_status = now(), "in_progress"
    step.status, step.nudge_count = StepStatus.waiting_on_vendor, 0
    c.status = CandidateStatus.waiting_on_vendor
    log_event(s, c, "bg_form_completed", Actor.candidate, order_id=order_id)
    body, en = template("bg_form_received", c.preferred_language, first_name=c.first_name)
    send(s, c, body, en, Sender.system)
    s.commit()
    return c


def bg_result(s: Session, order_id: str, status: str, summary: str) -> Optional[Candidate]:
    """Called after Claude extracts the result from the vendor's email. Code decides what happens."""
    bc = s.exec(select(BackgroundCheck).where(BackgroundCheck.vendor_order_id == order_id)).first()
    if not bc:
        return None
    step = s.get(Step, bc.step_id)
    c = s.get(Candidate, step.candidate_id)
    bc.report_received_at, bc.report_status, bc.flags = now(), status, summary
    step.completed_at, step.flag_note = now(), None
    log_event(s, c, "bg_result_received", Actor.vendor, order_id=order_id, status=status, summary=summary)
    if status == "clear":
        step.status, step.result = StepStatus.passed, StepResult.pass_
        body, en = template("bg_clear", c.preferred_language, first_name=c.first_name)
        send(s, c, body, en, Sender.system)
        advance(s, c, Stage.drug_test)
    else:  # consider: a human decides (never auto-reject; FCRA adverse-action rules apply)
        step.status, step.result = StepStatus.passed, StepResult.flag
        c.status = CandidateStatus.needs_review
        create_task(s, c, "review_background_flag", f"Background check needs review: {summary[:140]}", priority=1)
        body, en = template("under_review", c.preferred_language, first_name=c.first_name)
        send(s, c, body, en, Sender.system)
    s.commit()
    return c


# ---------- Drug test ----------

def nearby_clinics(s: Session, c: Candidate) -> list[Clinic]:
    return s.exec(select(Clinic).where(Clinic.depot_id == c.depot_id)).all()


def _enter_drug_test(s: Session, c: Candidate, step: Step) -> None:
    case = vendors.open_drug_test_case(c.id)
    s.add(DrugTest(step_id=step.id, vendor_case_id=case["case_id"], booking_link=case["booking_link"], auth_sent_at=now()))
    step.status = StepStatus.waiting_on_candidate
    c.status = CandidateStatus.waiting_on_candidate
    clinics = "\n".join(f"• {cl.name}, {cl.address} ({cl.hours})" for cl in nearby_clinics(s, c))
    log_event(s, c, "drug_test_case_opened", Actor.system, case_id=case["case_id"])
    body, en = template("drug_start", c.preferred_language, link=case["booking_link"], clinics=clinics)
    send(s, c, body, en, Sender.system)


def _drug(s: Session, case_id: str) -> tuple[Optional[DrugTest], Optional[Step], Optional[Candidate]]:
    dt = s.exec(select(DrugTest).where(DrugTest.vendor_case_id == case_id)).first()
    if not dt:
        return None, None, None
    step = s.get(Step, dt.step_id)
    return dt, step, s.get(Candidate, step.candidate_id)


def drug_event(s: Session, case_id: str, event: str, clinic_id: Optional[int] = None,
               appointment_at: Optional[datetime] = None, result: Optional[str] = None) -> Optional[Candidate]:
    """Vendor integration events: appointment_booked, collected, no_show, result."""
    dt, step, c = _drug(s, case_id)
    if not dt:
        return None
    lang = c.preferred_language

    if event == "appointment_booked":
        dt.auth_signed_at = dt.auth_signed_at or now()
        dt.clinic_id, dt.appointment_at = clinic_id, appointment_at
        dt.reminded_day_before = dt.reminded_morning_of = False
        step.nudge_count = 0  # booked: stop generic nudges, appointment reminders take over
        clinic = s.get(Clinic, clinic_id)
        log_event(s, c, "drug_test_booked", Actor.candidate, clinic=clinic.name, at=appointment_at.isoformat())
        body, en = template("drug_booked", lang, clinic=clinic.name, when=fmt_when(appointment_at))
        send(s, c, body, en, Sender.system)

    elif event == "collected":
        dt.collected_at = now()
        step.status, step.nudge_count = StepStatus.waiting_on_vendor, 0
        c.status = CandidateStatus.waiting_on_vendor
        log_event(s, c, "drug_test_collected", Actor.vendor, case_id=case_id)
        body, en = template("drug_collected", lang, first_name=c.first_name)
        send(s, c, body, en, Sender.system)

    elif event == "no_show":
        dt.no_show_count += 1
        dt.appointment_at = None
        step.nudge_count = 0
        step.started_at = now()  # restart follow-ups from today
        log_event(s, c, "drug_test_no_show", Actor.vendor, count=dt.no_show_count)
        body, en = template("drug_no_show", lang, first_name=c.first_name, link=dt.booking_link)
        send(s, c, body, en, Sender.system)

    elif event == "result":
        dt.result, dt.result_received_at = result, now()
        step.completed_at, step.flag_note = now(), None
        log_event(s, c, "drug_test_result", Actor.vendor, result=result)
        if result == "negative":
            step.status, step.result = StepStatus.passed, StepResult.pass_
            body, en = template("drug_negative", lang, first_name=c.first_name)
            send(s, c, body, en, Sender.system)
            advance(s, c, Stage.cdl_permit)
        else:  # non-negative: recruiter decides (never auto-reject)
            step.status, step.result = StepStatus.passed, StepResult.flag
            c.status = CandidateStatus.needs_review
            create_task(s, c, "review_drug_result", f"Drug test result: {result.replace('_', '-')}", priority=1)
            body, en = template("under_review", lang, first_name=c.first_name)
            send(s, c, body, en, Sender.system)
    s.commit()
    return c

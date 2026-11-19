"""Stage transitions for background check and drug test.

Every function here is called by code (vendor events, recruiter actions, the engine), never by
Claude. Each one updates the step, tells the candidate what happens next, and logs an event.
"""

import base64
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from . import ai, vendors, workday
from .config import DMV_PERMIT_LINK, LOCAL_TZ, OFFER_TERMS, TRAINING_HOUR, TRAINING_WEEKDAY
from .conversation import create_task, log_event, send, template
from .models import (Actor, BackgroundCheck, Candidate, CandidateStatus, Clinic, Depot, DrugTest, Offer, PermitCheck,
                     Sender, SkillsTest, Stage, Step, StepResult, StepStatus, Training, now)

NEXT_STAGE = {Stage.screening: Stage.background_check, Stage.background_check: Stage.drug_test,
              Stage.drug_test: Stage.cdl_permit, Stage.cdl_permit: Stage.training,
              Stage.training: Stage.skills_test, Stage.skills_test: Stage.offer, Stage.offer: Stage.hired}
UPLOADS = Path(__file__).resolve().parent.parent / "uploads"


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
    elif to == Stage.cdl_permit:
        _enter_permit(s, c, step)
    elif to == Stage.training:
        _enter_training(s, c, step)
    elif to == Stage.skills_test:
        _enter_skills(s, c, step)
    elif to == Stage.offer:
        _enter_offer(s, c, step)
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



def _finish(step: Step, result: StepResult = StepResult.pass_) -> None:
    step.status = StepStatus.passed if result != StepResult.fail else StepStatus.failed
    step.result, step.completed_at, step.flag_note = result, now(), None


# ---------- CDL permit ----------

def _enter_permit(s: Session, c: Candidate, step: Step) -> None:
    s.add(PermitCheck(step_id=step.id))
    step.status, c.status = StepStatus.waiting_on_candidate, CandidateStatus.waiting_on_candidate
    body, en = template("permit_start", c.preferred_language, link=DMV_PERMIT_LINK)
    send(s, c, body, en, Sender.system)


def permit_photo_received(s: Session, c: Candidate, data: bytes, media_type: str) -> None:
    """Candidate sent a permit photo. Claude reads it; code checks it; a recruiter verifies."""
    step = current_step(s, c)
    pc = s.get(PermitCheck, step.id) or PermitCheck(step_id=step.id)
    UPLOADS.mkdir(exist_ok=True)
    name = f"permit-{c.id}-{uuid.uuid4().hex[:8]}.{media_type.split('/')[-1].replace('jpeg', 'jpg')}"
    (UPLOADS / name).write_bytes(data)
    pc.image_path, pc.received_at = name, now()
    try:
        read = ai.read_permit(base64.b64encode(data).decode(), media_type)
        pc.extracted = read.model_dump()
        pc.mismatches = _permit_mismatches(c, read)
    except Exception as e:
        pc.extracted, pc.mismatches = {}, [f"Couldn't read the photo automatically ({str(e)[:60]})"]
    s.add(pc)
    step.status, step.nudge_count = StepStatus.waiting_on_vendor, 0  # waiting on our own recruiter now
    c.status = CandidateStatus.needs_review
    issues = "; ".join(pc.mismatches) if pc.mismatches else "details match"
    create_task(s, c, "review_permit", f"Verify CDL permit photo ({issues})", priority=1 if pc.mismatches else 2)
    log_event(s, c, "permit_photo_received", Actor.candidate, mismatches=pc.mismatches)
    body, en = template("permit_received", c.preferred_language, first_name=c.first_name)
    send(s, c, body, en, Sender.system)
    s.commit()


def _permit_mismatches(c: Candidate, r: "ai.PermitRead") -> list[str]:
    issues = []
    if not r.legible:
        return ["Photo isn't legible"]
    if not r.is_cdl_learner_permit:
        issues.append("Doesn't look like a CDL learner's permit")
    if r.name and c.last_name and c.last_name.lower() not in r.name.lower():
        issues.append(f"Name on permit “{r.name}” doesn't match {c.first_name} {c.last_name}")
    if r.expiration_date:
        try:
            if date.fromisoformat(r.expiration_date) < now().date():
                issues.append(f"Expired {r.expiration_date}")
        except ValueError:
            pass
    return issues


def permit_decision(s: Session, c: Candidate, verified: bool) -> None:
    step = current_step(s, c)
    pc = s.get(PermitCheck, step.id)
    if verified:
        pc.verified_at = now()
        _finish(step)
        log_event(s, c, "permit_verified", Actor.recruiter)
        advance(s, c, Stage.training)
    else:
        step.status, step.started_at, step.nudge_count = StepStatus.waiting_on_candidate, now(), 0
        c.status = CandidateStatus.waiting_on_candidate
        log_event(s, c, "permit_new_photo_requested", Actor.recruiter)
        body, en = template("permit_new_photo", c.preferred_language, first_name=c.first_name)
        send(s, c, body, en, Sender.system)


# ---------- Training ----------

def _next_cohort() -> datetime:
    local = now().astimezone(ZoneInfo(LOCAL_TZ))
    days = (TRAINING_WEEKDAY - local.weekday()) % 7 or 7
    start = (local + timedelta(days=days)).replace(hour=TRAINING_HOUR, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc)


def _enter_training(s: Session, c: Candidate, step: Step) -> None:
    start, link = _next_cohort(), vendors.training_session(c.id)["link"]
    s.add(Training(step_id=step.id, cohort_start=start, session_link=link))
    step.status, c.status = StepStatus.in_progress, CandidateStatus.in_progress  # no nudging; session reminders instead
    log_event(s, c, "training_enrolled", Actor.system, cohort_start=start.isoformat())
    body, en = template("training_start", c.preferred_language, when=fmt_when(start), link=link)
    send(s, c, body, en, Sender.system)


def training_completed(s: Session, c: Candidate, by: Optional[int] = None) -> None:
    step = current_step(s, c)
    s.get(Training, step.id).completed_at = now()
    _finish(step)
    log_event(s, c, "training_completed", Actor.recruiter, actor_id=by)
    advance(s, c, Stage.skills_test)


# ---------- Skills test ----------

def _enter_skills(s: Session, c: Candidate, step: Step) -> None:
    t = vendors.skills_test(c.id)
    s.add(SkillsTest(step_id=step.id, test_id=t["test_id"], test_link=t["link"], attempts=1))
    step.status, c.status = StepStatus.waiting_on_candidate, CandidateStatus.waiting_on_candidate
    body, en = template("skills_start", c.preferred_language, first_name=c.first_name, link=t["link"])
    send(s, c, body, en, Sender.system)


def skills_result(s: Session, test_id: str, result: str, score: Optional[int]) -> Optional[Candidate]:
    st = s.exec(select(SkillsTest).where(SkillsTest.test_id == test_id)).first()
    if not st:
        return None
    step = s.get(Step, st.step_id)
    c = s.get(Candidate, step.candidate_id)
    st.result, st.score, st.result_received_at = result, score, now()
    log_event(s, c, "skills_test_result", Actor.vendor, result=result, score=score)
    if result == "pass":
        _finish(step)
        advance(s, c, Stage.offer)
    else:
        step.status, step.result = StepStatus.passed, StepResult.flag
        c.status = CandidateStatus.needs_review
        create_task(s, c, "review_skills_test", f"Skills test failed (score {score}): allow a retest?", priority=1)
        body, en = template("under_review", c.preferred_language, first_name=c.first_name)
        send(s, c, body, en, Sender.system)
    s.commit()
    return c


def allow_retest(s: Session, c: Candidate) -> None:
    step = current_step(s, c)
    st = s.get(SkillsTest, step.id)
    st.attempts, st.result, st.score = st.attempts + 1, None, None
    step.status, step.result, step.started_at, step.nudge_count = StepStatus.waiting_on_candidate, None, now(), 0
    c.status = CandidateStatus.waiting_on_candidate
    log_event(s, c, "skills_retest_allowed", Actor.recruiter, attempt=st.attempts)
    body, en = template("skills_retest", c.preferred_language, first_name=c.first_name, link=st.test_link)
    send(s, c, body, en, Sender.system)


# ---------- Offer ----------

def _enter_offer(s: Session, c: Candidate, step: Step) -> None:
    o = vendors.offer_letter(c.id)
    depot = s.get(Depot, c.depot_id)
    terms = {**OFFER_TERMS, "depot": f"{depot.name} ({depot.city})" if depot else ""}
    s.add(Offer(step_id=step.id, offer_id=o["offer_id"], sign_link=o["link"], terms=terms, sent_at=now()))
    step.status, c.status = StepStatus.waiting_on_candidate, CandidateStatus.waiting_on_candidate
    log_event(s, c, "offer_sent", Actor.system, offer_id=o["offer_id"], terms=terms)
    body, en = template("offer_start", c.preferred_language, first_name=c.first_name, link=o["link"])
    send(s, c, body, en, Sender.system)


def offer_response(s: Session, offer_id: str, signed: bool) -> Optional[Candidate]:
    o = s.exec(select(Offer).where(Offer.offer_id == offer_id)).first()
    if not o or o.signed_at or o.declined_at:
        return None
    step = s.get(Step, o.step_id)
    c = s.get(Candidate, step.candidate_id)
    if signed:
        o.signed_at = now()
        _finish(step)
        log_event(s, c, "offer_signed", Actor.candidate, offer_id=offer_id)
        log_event(s, c, "stage_changed", Actor.system, **{"from": c.stage.value, "to": Stage.hired.value})
        c.stage, c.stage_entered_at, c.status = Stage.hired, now(), CandidateStatus.hired
        workday.push_disposition(s, c, "hired", "Offer signed")
        body, en = template("hired", c.preferred_language, first_name=c.first_name)
        send(s, c, body, en, Sender.system)
    else:
        o.declined_at = now()
        step.status, step.result = StepStatus.passed, StepResult.flag
        c.status = CandidateStatus.needs_review
        log_event(s, c, "offer_declined", Actor.candidate, offer_id=offer_id)
        create_task(s, c, "offer_declined", "Candidate declined the offer", priority=1)
    s.commit()
    return c

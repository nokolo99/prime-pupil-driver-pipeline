"""Demo-only controls: the simulated clock and a view of what we 'sent' to Workday."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import clock
from ..db import get_session
from ..engine import tick
from ..models import Setting, WorkdayOutbox

router = APIRouter(prefix="/api/demo", tags=["demo controls"])


def save_offset(s: Session) -> None:
    row = s.get(Setting, "clock_offset_days") or Setting(key="clock_offset_days", value="0")
    row.value = str(clock.offset_days())
    s.add(row)
    s.commit()


@router.get("/clock")
def get_clock():
    from ..models import now
    return {"offset_days": clock.offset_days(), "now": now().isoformat()}


class Advance(BaseModel):
    days: int


@router.post("/clock/advance")
def advance_clock(a: Advance, s: Session = Depends(get_session)):
    """Move time forward in 6-hour steps, running the engine after each, so every reminder
    that would have fired in that window fires in order (and quiet hours are respected)."""
    actions = 0
    for _ in range(a.days * 4):
        clock.set_offset(clock.offset_days() + 0.25)
        actions += tick(s)
    save_offset(s)
    return {"offset_days": clock.offset_days(), "actions": actions}


@router.post("/clock/reset")
def reset_clock(s: Session = Depends(get_session)):
    clock.set_offset(0)
    save_offset(s)
    return {"offset_days": 0}


@router.post("/tick")
def run_tick(s: Session = Depends(get_session)):
    return {"actions": tick(s)}


@router.get("/workday-outbox")
def outbox(s: Session = Depends(get_session)):
    return s.exec(select(WorkdayOutbox).order_by(WorkdayOutbox.id.desc()).limit(50)).all()


class CallReq(BaseModel):
    phone: str


@router.get("/voice-status")
def voice_status():
    from .. import telephony
    return {"twilio": telephony.twilio_ready(), "public_url": telephony.PUBLIC_URL, "ready": telephony.voice_ready()}


@router.post("/call")
def call_now(r: CallReq, s: Session = Depends(get_session)):
    """'Call me now': the AI calls this candidate immediately."""
    from fastapi import HTTPException
    from .. import telephony
    from ..conversation import log_event
    from ..models import Actor, Candidate
    from ..phones import normalize_us
    try:
        phone = normalize_us(r.phone)
    except ValueError as e:
        raise HTTPException(422, str(e))
    c = s.exec(select(Candidate).where(Candidate.phone == phone).order_by(Candidate.created_at.desc())).first()
    if not c:
        raise HTTPException(404, "No applicant with this phone. Submit a Workday application first.")
    if not telephony.voice_ready():
        raise HTTPException(400, "Voice not configured (Twilio credentials / ngrok).")
    from twilio.base.exceptions import TwilioRestException
    try:
        sid = telephony.place_call(c.phone, c.id, "demo")
    except TwilioRestException as e:
        raise HTTPException(400, f"Twilio couldn't place the call: {e.msg}")
    log_event(s, c, "ai_call_placed", Actor.system, reason="demo", call_sid=sid)
    s.commit()
    return {"call_sid": sid}


# ---------- Demo: reset / force a candidate's progress ----------

class CandidateReq(BaseModel):
    phone: str


class StageReq(BaseModel):
    phone: str
    stage: str


def _find(s: Session, phone: str):
    from fastapi import HTTPException
    from ..models import Candidate
    from ..phones import normalize_us
    try:
        phone = normalize_us(phone)
    except ValueError as e:
        raise HTTPException(422, str(e))
    c = s.exec(select(Candidate).where(Candidate.phone == phone).order_by(Candidate.created_at.desc())).first()
    if not c:
        raise HTTPException(404, "No applicant with this phone.")
    return c


@router.post("/candidate/restart")
def restart_candidate(r: CandidateReq, s: Session = Depends(get_session)):
    """Wipe this candidate's progress and start over as a fresh applicant (same Workday record)."""
    from sqlmodel import delete
    from ..conversation import intake_applicant
    from ..models import (BackgroundCheck, Candidate, DrugTest, Event, Message, ScreeningResult, Step, Task,
                          WorkdayOutbox)
    c = _find(s, r.phone)
    info = dict(first_name=c.first_name, last_name=c.last_name, phone=c.phone, email=c.email, depot_id=c.depot_id,
                language=c.preferred_language, sms_consent=c.sms_consent_at is not None, workday_id=c.workday_id)
    step_ids = [st.id for st in s.exec(select(Step).where(Step.candidate_id == c.id)).all()]
    for model in (ScreeningResult, BackgroundCheck, DrugTest):
        s.exec(delete(model).where(model.step_id.in_(step_ids)))
    for model in (Step, Message, Event, Task, WorkdayOutbox):
        s.exec(delete(model).where(model.candidate_id == c.id))
    s.delete(c)
    s.commit()
    new = intake_applicant(s, **info)
    return {"candidate_id": new.id}


@router.post("/candidate/stage")
def force_stage(r: StageReq, s: Session = Depends(get_session)):
    """Place the candidate at a stage; earlier steps are marked passed. Demo shortcut only."""
    from fastapi import HTTPException
    from ..conversation import log_event
    from ..models import (STAGE_ORDER, Actor, CandidateStatus, ScreeningResult, Stage, Step, StepResult,
                          StepStatus, Task, TaskStatus, now)
    c = _find(s, r.phone)
    try:
        target = Stage(r.stage)
    except ValueError:
        raise HTTPException(422, f"Unknown stage {r.stage}")
    t = now()
    existing = {st.stage: st for st in s.exec(select(Step).where(Step.candidate_id == c.id)).all()}
    for stage in STAGE_ORDER[1:STAGE_ORDER.index(target)]:  # skip 'application'
        st = existing.get(stage) or Step(candidate_id=c.id, stage=stage)
        st.status, st.result, st.completed_at = StepStatus.passed, StepResult.pass_, t
        st.started_at = st.started_at or t
        s.add(st)
        if stage == Stage.screening:
            s.flush()
            sr = s.get(ScreeningResult, st.id) or ScreeningResult(step_id=st.id)
            sr.is_21_plus, sr.has_valid_license, sr.years_licensed = True, True, sr.years_licensed or 5
            sr.recent_violations, sr.availability_ok = False, True
            sr.has_cdl_or_permit = bool(sr.has_cdl_or_permit)
            sr.knockout_flags = []
            s.add(sr)
    if target != Stage.hired:
        cur = existing.get(target) or Step(candidate_id=c.id, stage=target)
        cur.status, cur.result, cur.completed_at = StepStatus.waiting_on_candidate, None, None
        cur.started_at, cur.nudge_count, cur.last_nudged_at = t, 0, None
        s.add(cur)
        if target == Stage.screening:
            s.flush()
            if not s.get(ScreeningResult, cur.id):
                s.add(ScreeningResult(step_id=cur.id))
    for task in s.exec(select(Task).where(Task.candidate_id == c.id, Task.status == TaskStatus.open)).all():
        task.status, task.resolution, task.resolved_at = TaskStatus.resolved, "demo_reset", t
    c.stage, c.stage_entered_at = target, t
    c.status = CandidateStatus.hired if target == Stage.hired else CandidateStatus.waiting_on_candidate
    c.drop_reason = c.drop_note = None
    log_event(s, c, "demo_stage_forced", Actor.system, to=target.value)
    s.commit()
    return {"stage": target.value}

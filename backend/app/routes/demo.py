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
    """Move time forward in 2-hour steps, running the engine after each, so every reminder
    that would have fired in that window fires in order (and quiet hours are respected)."""
    actions = 0
    for _ in range(a.days * 12):
        clock.set_offset(clock.offset_days() + 1 / 12)
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
    from .. import messaging, telephony
    return {"twilio": telephony.twilio_ready(), "public_url": telephony.PUBLIC_URL, "ready": telephony.voice_ready(),
            "providers": {"sms": messaging.provider_for("sms"), "whatsapp": messaging.provider_for("whatsapp")},
            "vonage_ready": messaging.vonage_ready()}


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
    if target not in (Stage.screening, Stage.hired):
        for task in s.exec(select(Task).where(Task.candidate_id == c.id, Task.status == TaskStatus.open)).all():
            task.status, task.resolution, task.resolved_at = TaskStatus.resolved, "demo_reset", t
        c.drop_reason = c.drop_note = None
        c.stage = STAGE_ORDER[STAGE_ORDER.index(target) - 1]
        from ..stages import advance
        advance(s, c, target)  # real entry actions: order BG / open drug case, text the link
        log_event(s, c, "demo_stage_forced", Actor.system, to=target.value)
        s.commit()
        return {"stage": target.value}
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



# ---------- Demo: vendor events for the selected candidate ----------

@router.get("/vendor-context")
def vendor_context(phone: str, s: Session = Depends(get_session)):
    from ..models import BackgroundCheck, DrugTest, Step
    from .. import vendors
    c = _find(s, phone)
    out = {"stage": c.stage.value, "status": c.status.value, "bg": None, "drug": None}
    for st in s.exec(select(Step).where(Step.candidate_id == c.id)).all():
        bc, dt = s.get(BackgroundCheck, st.id), s.get(DrugTest, st.id)
        if bc:
            out["bg"] = {"order_id": bc.vendor_order_id, "form_link": bc.form_link, "form_completed": bool(bc.form_completed_at),
                         "report_status": bc.report_status,
                         "email_clear": vendors.sample_result_email(bc.vendor_order_id, c.first_name, c.last_name, True),
                         "email_flagged": vendors.sample_result_email(bc.vendor_order_id, c.first_name, c.last_name, False)}
        if dt:
            out["drug"] = {"case_id": dt.vendor_case_id, "booking_link": dt.booking_link,
                           "appointment_at": dt.appointment_at, "collected": bool(dt.collected_at), "result": dt.result}
        from ..models import Offer, SkillsTest
        sk, of = s.get(SkillsTest, st.id), s.get(Offer, st.id)
        if sk:
            out["skills"] = {"test_id": sk.test_id, "link": sk.test_link, "result": sk.result, "attempts": sk.attempts}
        if of:
            out["offer"] = {"offer_id": of.offer_id, "link": of.sign_link, "signed": bool(of.signed_at), "declined": bool(of.declined_at)}
    out["candidate_id"] = c.id
    return out



@router.get("/sample-permit")
def sample_permit(phone: str, s: Session = Depends(get_session)):
    """Generates a fake CDL learner's permit photo with this candidate's name (demo only)."""
    import io
    from datetime import timedelta
    from fastapi.responses import Response as R
    from PIL import Image, ImageDraw
    from ..models import now
    c = _find(s, phone)
    img = Image.new("RGB", (860, 540), (233, 240, 247))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 860, 90], fill=(23, 63, 115))
    d.text((30, 25), "NEW YORK STATE  ·  COMMERCIAL LEARNER PERMIT", fill="white", font_size=30)
    d.rectangle([30, 120, 250, 400], fill=(190, 200, 210))
    d.text((80, 250), "PHOTO", fill=(110, 120, 130), font_size=28)
    lines = [("CLP", "Class B   ·   Endorsements: P, S"), ("NAME", f"{c.last_name.upper()}, {c.first_name.upper()}"),
             ("ID NO", f"CLP-{c.id:03d}-{c.phone[-4:]}-77"), ("DOB", "01/01/1980"),
             ("ISSUED", now().strftime("%m/%d/%Y")), ("EXPIRES", (now() + timedelta(days=180)).strftime("%m/%d/%Y"))]
    for i, (k, v) in enumerate(lines):
        d.text((290, 125 + i * 48), k, fill=(90, 100, 110), font_size=18)
        d.text((400, 120 + i * 48), v, fill=(20, 20, 20), font_size=28)
    d.text((30, 470), "SAMPLE FOR PROTOTYPE DEMO · NOT A REAL DOCUMENT", fill=(160, 40, 40), font_size=20)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return R(buf.getvalue(), media_type="image/png")


@router.post("/send-sample-permit")
def send_sample_permit(r: CandidateReq, s: Session = Depends(get_session)):
    from ..models import Channel, Message
    from ..stages import permit_photo_received
    c = _find(s, r.phone)
    if c.stage.value != "cdl_permit":
        from fastapi import HTTPException
        raise HTTPException(400, "Candidate isn't at the CDL permit step.")
    png = sample_permit(r.phone, s).body
    s.add(Message(candidate_id=c.id, direction="in", channel=Channel.web, sender="candidate", body="[photo]"))
    permit_photo_received(s, c, png, "image/png")
    return {"ok": True}



@router.post("/seed")
def seed(s: Session = Depends(get_session)):
    """Load ~1,500 realistic demo candidates (150 days) (replaces any previous demo data)."""
    clear_seed(s)
    from ..demo_seed import seed_demo
    return seed_demo(s)


@router.post("/seed/clear")
def clear_seed(s: Session = Depends(get_session)):
    from sqlmodel import delete
    from ..models import (BackgroundCheck, Candidate, DrugTest, Event, Message, Offer, PermitCheck, ScreeningResult,
                          SkillsTest, Step, Task, Training, WorkdayOutbox)
    ids = [c.id for c in s.exec(select(Candidate).where(Candidate.source == "demo_seed")).all()]
    if not ids:
        return {"cleared": 0}
    step_ids = [st.id for st in s.exec(select(Step).where(Step.candidate_id.in_(ids))).all()]
    for model in (ScreeningResult, BackgroundCheck, DrugTest, PermitCheck, Training, SkillsTest, Offer):
        s.exec(delete(model).where(model.step_id.in_(step_ids)))
    for model in (Step, Message, Event, Task, WorkdayOutbox):
        s.exec(delete(model).where(model.candidate_id.in_(ids)))
    s.exec(delete(Candidate).where(Candidate.id.in_(ids)))
    s.commit()
    return {"cleared": len(ids)}

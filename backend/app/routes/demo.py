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
    c = s.exec(select(Candidate).where(Candidate.phone == r.phone).order_by(Candidate.created_at.desc())).first()
    if not c:
        raise HTTPException(404, "No applicant with this phone. Submit a Workday application first.")
    if not telephony.voice_ready():
        raise HTTPException(400, "Voice not configured (Twilio credentials / ngrok).")
    sid = telephony.place_call(c.phone, c.id, "demo")
    log_event(s, c, "ai_call_placed", Actor.system, reason="demo", call_sid=sid)
    s.commit()
    return {"call_sid": sid}

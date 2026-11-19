"""Browser phone simulator: stands in for SMS until Twilio is plugged in (increment 3)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..conversation import handle_inbound
from ..db import get_session
from ..models import Candidate, Channel, Message

router = APIRouter(prefix="/api/sim", tags=["simulator"])


def _by_phone(s: Session, phone: str) -> Candidate | None:
    return s.exec(select(Candidate).where(Candidate.phone == phone).order_by(Candidate.created_at.desc())).first()


@router.get("/messages")
def messages(phone: str, session: Session = Depends(get_session)):
    c = _by_phone(session, phone)
    if not c:
        return []
    return session.exec(select(Message).where(Message.candidate_id == c.id).order_by(Message.created_at)).all()


class Inbound(BaseModel):
    phone: str
    body: str


@router.post("/inbound")
def inbound(m: Inbound, session: Session = Depends(get_session)):
    c = _by_phone(session, m.phone)
    if not c:
        raise HTTPException(404, "No applicant with this phone. Submit a Workday application first.")
    handle_inbound(session, c, m.body, Channel.web)
    return {"ok": True}

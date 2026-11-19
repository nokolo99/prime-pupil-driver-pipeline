"""Browser phone simulator: stands in for SMS until Twilio is plugged in (increment 3)."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from ..conversation import handle_inbound
from ..db import get_session
from ..models import Candidate, Channel, Message
from ..phones import normalize_us

router = APIRouter(prefix="/api/sim", tags=["simulator"])


def _by_phone(s: Session, phone: str) -> Candidate | None:
    try:
        phone = normalize_us(phone)
    except ValueError:
        return None
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



@router.post("/inbound-photo")
async def inbound_photo(phone: str = Form(...), photo: UploadFile = File(...), session: Session = Depends(get_session)):
    """Simulator stand-in for a picture message (MMS)."""
    from ..stages import permit_photo_received
    c = _by_phone(session, phone)
    if not c:
        raise HTTPException(404, "No applicant with this phone.")
    session.add(Message(candidate_id=c.id, direction="in", channel=Channel.web, sender="candidate", body="[photo]"))
    if c.stage.value != "cdl_permit":
        session.commit()
        return {"ok": True, "note": "Photo received, but no step needs a photo right now."}
    permit_photo_received(session, c, await photo.read(), photo.content_type or "image/jpeg")
    return {"ok": True}


@router.get("/media/{name}")
def media(name: str):
    from ..stages import UPLOADS
    path = (UPLOADS / name).resolve()
    if path.parent != UPLOADS.resolve() or not path.exists():
        raise HTTPException(404)
    return FileResponse(path)

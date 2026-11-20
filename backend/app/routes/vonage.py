"""Vonage Messages API webhooks (WhatsApp sandbox / SMS). Same handling as Twilio via process_incoming()."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlmodel import Session, select

from .. import messaging
from ..conversation import log_event
from ..db import get_session
from ..models import Actor, Candidate, Channel, Message
from .sms import process_incoming

log = logging.getLogger(__name__)
router = APIRouter(prefix="/vonage", tags=["vonage (webhooks)"])


@router.post("/inbound")
async def inbound(request: Request, s: Session = Depends(get_session)):
    if not messaging.vonage_valid_webhook(request.headers.get("Authorization", "")):
        raise HTTPException(401, "Invalid Vonage signature")
    m = await request.json()
    channel = Channel.whatsapp if m.get("channel") == "whatsapp" else Channel.sms
    phone = "+" + str(m.get("from", "")).lstrip("+")
    body = (m.get("text") or (m.get("image") or {}).get("caption") or "").strip()
    image = m.get("image") if m.get("message_type") == "image" else None

    def photo():
        url = image["url"]
        mtype = "image/png" if url.lower().split("?")[0].endswith(".png") else "image/jpeg"
        return messaging.vonage_download(url), mtype

    process_incoming(s, phone, body, channel, photo if image else None)
    return Response(status_code=200)


@router.post("/status")
async def status(request: Request, s: Session = Depends(get_session)):
    if not messaging.vonage_valid_webhook(request.headers.get("Authorization", "")):
        raise HTTPException(401, "Invalid Vonage signature")
    m = await request.json()
    st = m.get("status")
    if st in ("rejected", "undeliverable", "failed"):
        msg = s.exec(select(Message).where(Message.provider_id == m.get("message_uuid"))).first()
        if msg:
            log_event(s, s.get(Candidate, msg.candidate_id), "sms_undelivered", Actor.system,
                      status=st, error=str(m.get("error", ""))[:200], provider="vonage")
            s.commit()
        log.warning("Vonage message %s %s: %s", m.get("message_uuid"), st, m.get("error"))
    return Response(status_code=200)

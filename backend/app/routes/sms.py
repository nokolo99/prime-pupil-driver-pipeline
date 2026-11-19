"""Inbound SMS (Twilio webhook) and delivery status. Same conversation brain as voice and the simulator.

Opt-out keywords (STOP, etc.) are also handled by Twilio itself, which sends the required
confirmation; we record the opt-out so the engine stops all follow-ups and calls.
"""

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlmodel import Session, select

from ..conversation import handle_inbound, log_event
from ..db import get_session
from ..models import Actor, Candidate, Channel, Message
from .voice import _verified_form

log = logging.getLogger(__name__)
router = APIRouter(prefix="/sms", tags=["sms (Twilio webhooks)"])

STOP_WORDS = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit", "revoke", "optout"}
START_WORDS = {"start", "unstop", "yes"}
EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


@router.post("/inbound")
async def inbound(request: Request, s: Session = Depends(get_session)):
    form = await _verified_form(request)
    phone, body = form.get("From", ""), (form.get("Body") or "").strip()
    c = s.exec(select(Candidate).where(Candidate.phone == phone).order_by(Candidate.created_at.desc())).first()
    if not c:
        log.info("SMS from unknown number %s: %r", phone, body[:60])
        return Response(EMPTY_TWIML, media_type="application/xml")

    word = body.lower().strip(" .!")
    if word in STOP_WORDS:
        s.add(Message(candidate_id=c.id, direction="in", channel=Channel.sms, sender="candidate", body=body))
        c.opted_out = True
        log_event(s, c, "opted_out", Actor.candidate, keyword=word)
        s.commit()
    elif word in START_WORDS and c.opted_out:
        s.add(Message(candidate_id=c.id, direction="in", channel=Channel.sms, sender="candidate", body=body))
        c.opted_out = False
        log_event(s, c, "opted_in", Actor.candidate, keyword=word)
        s.commit()
    else:
        handle_inbound(s, c, body, Channel.sms)  # replies are texted back by conversation.send()
    return Response(EMPTY_TWIML, media_type="application/xml")


@router.post("/status")
async def status(request: Request, s: Session = Depends(get_session)):
    """Delivery receipts. Failures (e.g. 30034 unregistered number) show up on the candidate timeline."""
    form = await _verified_form(request)
    st, sid = form.get("MessageStatus"), form.get("MessageSid")
    if st in ("failed", "undelivered"):
        m = s.exec(select(Message).where(Message.provider_id == sid)).first()
        if m:
            log_event(s, s.get(Candidate, m.candidate_id), "sms_undelivered", Actor.system,
                      error_code=form.get("ErrorCode"), status=st)
            s.commit()
        log.warning("SMS %s %s (error %s)", sid, st, form.get("ErrorCode"))
    return Response(status_code=204)

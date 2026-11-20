"""Inbound SMS (Twilio webhook) and delivery status. Same conversation brain as voice and the simulator.

Opt-out keywords (STOP, etc.) are also handled by Twilio itself, which sends the required
confirmation; we record the opt-out so the engine stops all follow-ups and calls.
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import Response
from sqlmodel import Session, select

from ..conversation import handle_inbound, log_event
from ..db import engine, get_session
from ..models import Actor, Candidate, Channel, Message
from .voice import _verified_form

log = logging.getLogger(__name__)
router = APIRouter(prefix="/sms", tags=["sms (Twilio webhooks)"])

STOP_WORDS = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit", "revoke", "optout"}
START_WORDS = {"start", "unstop", "yes"}
EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


_apply_link_sent: dict[str, float] = {}  # phone -> when we last sent them the apply link


def _reply_with_apply_link(phone: str, channel: Channel) -> None:
    """Someone messaged before applying (e.g. scanned the WhatsApp QR code): send them the career page.
    Their message also opens WhatsApp's 24-hour window, so our intro can follow once they apply.
    At most once an hour per number, so two bots can never loop."""
    import time
    from urllib.parse import quote
    from .. import messaging, telephony
    if time.time() - _apply_link_sent.get(phone, 0) < 3600 or not telephony.PUBLIC_URL:
        return
    _apply_link_sent[phone] = time.time()
    link = f"{telephony.PUBLIC_URL}/apply?phone={quote(phone)}&channel={channel.value}"
    body = (f"Hi! Thanks for your interest in driving with Prime Pupil. Apply here, it takes about a minute: {link}\n\n"
            f"¡Hola! Gracias por tu interés en manejar con Prime Pupil. Postúlate aquí, toma un minuto: {link}")
    try:
        messaging.send_text(channel.value, phone, body)
    except Exception as e:
        log.warning("apply-link reply to %s failed: %s", phone, e)


def process_incoming_later(phone: str, body: str, channel: Channel, get_photo=None) -> None:
    """Run process_incoming after the webhook has answered (background task, worker thread): the Claude call
    and replies take seconds, and doing them inside the request would hold up the whole server."""
    try:
        with Session(engine) as s:
            process_incoming(s, phone, body, channel, get_photo)
    except Exception:
        log.exception("processing incoming message from %s failed", phone)


def process_incoming(s: Session, phone: str, body: str, channel: Channel, get_photo=None) -> None:
    """Provider-independent handling of an incoming text (Twilio or Vonage, SMS or WhatsApp).
    get_photo: optional callable returning (bytes, media_type) if the message has a picture."""
    c = s.exec(select(Candidate).where(Candidate.phone == phone).order_by(Candidate.created_at.desc())).first()
    if not c:
        log.info("Message from unknown number %s: %r", phone, body[:60])
        _reply_with_apply_link(phone, channel)
        return
    if channel == Channel.whatsapp and c.preferred_channel != channel:
        c.preferred_channel = channel  # they reached us on WhatsApp: keep the conversation there
        log_event(s, c, "channel_changed", Actor.candidate, to=channel.value)

    from ..stages import permit_awaiting_photo
    if get_photo and permit_awaiting_photo(s, c):
        from ..stages import permit_photo_received
        data, mtype = get_photo()
        s.add(Message(candidate_id=c.id, direction="in", channel=channel, sender="candidate", body=body or "[photo]"))
        permit_photo_received(s, c, data, mtype)
        return

    word = body.lower().strip(" .!")
    if word in STOP_WORDS:
        s.add(Message(candidate_id=c.id, direction="in", channel=channel, sender="candidate", body=body))
        c.opted_out = True
        log_event(s, c, "opted_out", Actor.candidate, keyword=word)
        s.commit()
    elif word in START_WORDS and c.opted_out:
        s.add(Message(candidate_id=c.id, direction="in", channel=channel, sender="candidate", body=body))
        c.opted_out = False
        log_event(s, c, "opted_in", Actor.candidate, keyword=word)
        s.commit()
    else:
        handle_inbound(s, c, body, channel)  # replies go back on the same channel via conversation.send()


@router.post("/inbound")
async def inbound(request: Request, bg: BackgroundTasks):
    """Twilio webhook: SMS and WhatsApp (WhatsApp senders look like 'whatsapp:+1...')."""
    import os
    form = await _verified_form(request)
    raw_from, body = form.get("From", ""), (form.get("Body") or "").strip()
    channel = Channel.whatsapp if raw_from.startswith("whatsapp:") else Channel.sms

    def photo():
        import httpx2 as httpx
        data = httpx.get(form.get("MediaUrl0"), auth=(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"]),
                         follow_redirects=True).content
        return data, form.get("MediaContentType0", "image/jpeg")

    has_photo = int(form.get("NumMedia", "0") or 0) > 0
    bg.add_task(process_incoming_later, raw_from.removeprefix("whatsapp:"), body, channel, photo if has_photo else None)
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

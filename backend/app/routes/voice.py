"""Voice calls, streaming (DESIGN.md: voice option B, Twilio ConversationRelay).

Twilio handles the real-time audio: Deepgram listens (auto-detects English/Spanish), ElevenLabs
speaks, and Twilio manages turn-taking and interruptions. Each time the caller finishes a turn,
Twilio sends us the transcript over a WebSocket; we run the SAME conversation logic as SMS
(conversation.handle_inbound) and send back the reply text to be spoken.
"""

import asyncio
import json
import logging
import secrets
from xml.sax.saxutils import quoteattr

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from sqlmodel import Session, select
from twilio.twiml.voice_response import VoiceResponse

from .. import telephony
from ..config import (RELAY_LANGUAGE, RELAY_TRANSCRIPTION_PROVIDER, RELAY_TTS_PROVIDER, RELAY_VOICES, VOICES)
from ..conversation import handle_inbound, log_event, template
from ..db import engine, get_session
from ..models import Actor, Candidate, CandidateStatus, Channel, Message, Sender, Stage

log = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice (Twilio webhooks)"])

LATER_WORDS = ("not now", "call me later", "busy right now", "ahora no", "más tarde", "mas tarde", "estoy ocupad")
# One-time tokens tying a WebSocket to the TwiML we generated (so random clients can't connect).
_call_tokens: dict[str, int] = {}


async def _verified_form(request: Request) -> dict:
    form = dict(await request.form())
    if telephony.twilio_ready() and telephony.PUBLIC_URL:
        url = telephony.PUBLIC_URL + request.url.path + (f"?{request.url.query}" if request.url.query else "")
        if not telephony.valid_signature(url, form, request.headers.get("X-Twilio-Signature", "")):
            raise HTTPException(403, "Invalid Twilio signature")
    return form


def _xml(body: str) -> Response:
    return Response(content=body, media_type="application/xml")


def _log_spoken(s: Session, c: Candidate, text: str, en: str) -> None:
    s.add(Message(candidate_id=c.id, direction="out", channel=Channel.voice, sender=Sender.system, body=text,
                  language=c.preferred_language, translation_en=en if en != text else None))


def _say_and_hangup(text: str, lang: str = "en") -> Response:
    vr = VoiceResponse()
    vr.say(text, voice=VOICES.get(lang, VOICES["en"])[0])
    vr.hangup()
    return _xml(str(vr))


def _relay_twiml(s: Session, c: Candidate, greeting_key: str) -> Response:
    """Hand the call to ConversationRelay, connected to our WebSocket."""
    if c.stage != Stage.screening or c.status in (CandidateStatus.needs_review, CandidateStatus.rejected, CandidateStatus.dropped):
        text, en = template("voice_later", c.preferred_language)
        _log_spoken(s, c, text, en); s.commit()
        return _say_and_hangup(text, c.preferred_language)

    greeting, en = template(greeting_key, c.preferred_language, first_name=c.first_name)
    _log_spoken(s, c, greeting, en)
    s.commit()
    token = secrets.token_urlsafe(16)
    _call_tokens[token] = c.id
    ws_url = telephony.PUBLIC_URL.replace("https://", "wss://") + f"/voice/relay?token={token}"
    tts_lang, voice = RELAY_VOICES.get(c.preferred_language, RELAY_VOICES["en"])
    languages = "".join(
        f'<Language code="{code}" ttsProvider="{RELAY_TTS_PROVIDER}" voice="{v}" '
        f'transcriptionProvider="{RELAY_TRANSCRIPTION_PROVIDER}" />'
        for code, v in RELAY_VOICES.values()
    )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?><Response>'
        '<Connect action="/voice/relay-ended">'
        f'<ConversationRelay url={quoteattr(ws_url)} welcomeGreeting={quoteattr(greeting)} '
        f'transcriptionLanguage="{RELAY_LANGUAGE}" transcriptionProvider="{RELAY_TRANSCRIPTION_PROVIDER}" '
        f'ttsLanguage="{tts_lang}" ttsProvider="{RELAY_TTS_PROVIDER}" voice="{voice}" interruptible="any">'
        f'{languages}</ConversationRelay>'
        '</Connect></Response>'
    )
    return _xml(body)


@router.post("/inbound")
async def inbound(request: Request, s: Session = Depends(get_session)):
    """Candidate calls our number."""
    form = await _verified_form(request)
    caller = form.get("From", "")
    c = s.exec(select(Candidate).where(Candidate.phone == caller).order_by(Candidate.created_at.desc())).first()
    if not c:
        return _say_and_hangup(template("voice_unknown_caller", "en")[0])
    log_event(s, c, "call_inbound", Actor.candidate, call_sid=form.get("CallSid"))
    return _relay_twiml(s, c, "voice_inbound_greeting")


@router.post("/answer")
async def answer(request: Request, candidate_id: int, reason: str = "follow_up", s: Session = Depends(get_session)):
    """Our outbound call connected (to a person or a voicemail)."""
    form = await _verified_form(request)
    c = s.get(Candidate, candidate_id)
    answered_by = form.get("AnsweredBy", "human")
    if answered_by.startswith("machine") or answered_by == "fax":
        text, en = template("voicemail", c.preferred_language, first_name=c.first_name)
        _log_spoken(s, c, text, en)
        log_event(s, c, "voicemail_left", Actor.system, reason=reason)
        s.commit()
        return _say_and_hangup(text, c.preferred_language)
    log_event(s, c, "call_answered", Actor.candidate, reason=reason, call_sid=form.get("CallSid"))
    return _relay_twiml(s, c, "voice_greeting")


@router.post("/relay-ended")
async def relay_ended(request: Request):
    await _verified_form(request)
    vr = VoiceResponse()
    vr.hangup()
    return _xml(str(vr))


def _process_turn(candidate_id: int, speech: str, lang: str | None) -> tuple[str, bool, str]:
    """Run one caller turn through the shared conversation logic. Returns (text, end call?, reply language)."""
    with Session(engine) as s:
        c = s.get(Candidate, candidate_id)
        low = speech.lower()
        if any(w in low for w in LATER_WORDS) and len(low.split()) <= 8:
            s.add(Message(candidate_id=c.id, direction="in", channel=Channel.voice, sender=Sender.candidate, body=speech))
            text, en = template("voice_later", c.preferred_language)
            _log_spoken(s, c, text, en); s.commit()
            return text, True, c.preferred_language

        last_id = s.exec(select(Message.id).where(Message.candidate_id == c.id).order_by(Message.id.desc())).first() or 0
        handle_inbound(s, c, speech, Channel.voice)  # same brain as SMS: code decides, Claude writes
        s.refresh(c)
        replies = s.exec(select(Message).where(Message.candidate_id == c.id, Message.direction == "out",
                                               Message.id > last_id).order_by(Message.id)).all()
        text = " ".join(m.body for m in replies) or template("voice_no_input", c.preferred_language)[0]
        over = c.stage != Stage.screening or c.status == CandidateStatus.needs_review
        if over:
            text = f"{text} {template('voice_goodbye', c.preferred_language)[0]}"
        return text, over, c.preferred_language


@router.websocket("/relay")
async def relay(ws: WebSocket, token: str):
    candidate_id = _call_tokens.pop(token, None)
    if candidate_id is None:
        await ws.close(code=1008)
        return
    await ws.accept()
    log.info("ConversationRelay connected for candidate %s", candidate_id)
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            kind = msg.get("type")
            if kind == "setup":
                continue
            if kind == "prompt" and msg.get("last", True):
                speech = (msg.get("voicePrompt") or "").strip()
                if not speech:
                    continue
                text, end, reply_lang = await asyncio.to_thread(_process_turn, candidate_id, speech, msg.get("lang"))
                tts_lang = RELAY_VOICES.get(reply_lang, RELAY_VOICES["en"])[0]
                # lang picks the matching <Language> voice (native Spanish voice for Spanish replies).
                await ws.send_text(json.dumps({"type": "text", "token": text, "last": True, "lang": tts_lang}))
                if end:
                    # Give the voice time to finish speaking before handing the call back.
                    await asyncio.sleep(min(2 + len(text) / 14, 20))
                    await ws.send_text(json.dumps({"type": "end"}))
            elif kind == "interrupt":
                log.info("caller interrupted after %sms", msg.get("durationUntilInterruptMs"))
            elif kind == "error":
                log.warning("ConversationRelay error: %s", msg.get("description"))
    except WebSocketDisconnect:
        log.info("ConversationRelay disconnected for candidate %s", candidate_id)

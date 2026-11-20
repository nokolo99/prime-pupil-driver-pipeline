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


VOICE_STAGES = (Stage.screening, Stage.background_check, Stage.drug_test, Stage.cdl_permit, Stage.skills_test, Stage.offer)
STEP_NAMES = {"en": {Stage.background_check: "your background check form", Stage.drug_test: "your drug test",
                     Stage.cdl_permit: "your CDL learner's permit", Stage.skills_test: "your skills test", Stage.offer: "your job offer"},
              "es": {Stage.background_check: "tu formulario de antecedentes", Stage.drug_test: "tu prueba de drogas",
                     Stage.cdl_permit: "tu permiso de aprendiz CDL", Stage.skills_test: "tu examen de habilidades", Stage.offer: "tu oferta de trabajo"}}


def _relay_twiml(s: Session, c: Candidate, greeting_key: str) -> Response:
    """Hand the call to ConversationRelay, connected to our WebSocket."""
    if c.stage not in VOICE_STAGES or c.status in (CandidateStatus.needs_review, CandidateStatus.rejected, CandidateStatus.dropped):
        text, en = template("voice_later", c.preferred_language)
        _log_spoken(s, c, text, en); s.commit()
        return _say_and_hangup(text, c.preferred_language)

    if c.stage == Stage.screening:
        greeting, en = template(greeting_key, c.preferred_language, first_name=c.first_name)
    else:
        step = STEP_NAMES.get(c.preferred_language, STEP_NAMES["en"])[c.stage]
        greeting, en = template("voice_greeting_stage", c.preferred_language, first_name=c.first_name, step=step)
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
        f'<Connect action="/voice/relay-ended?candidate_id={c.id}">'
        f'<ConversationRelay url={quoteattr(ws_url)} welcomeGreeting={quoteattr(greeting)} '
        f'transcriptionLanguage="{RELAY_LANGUAGE}" transcriptionProvider="{RELAY_TRANSCRIPTION_PROVIDER}" '
        f'ttsLanguage="{tts_lang}" ttsProvider="{RELAY_TTS_PROVIDER}" voice="{voice}" '
        # Echo/backchannel handling: don't treat the agent's own voice or "mm-hm" as the caller interrupting.
        'interruptible="any" interruptSensitivity="medium" echoPromptFiltering="true" ignoreBackchannel="true" '
        # A "hello?" while the greeting plays shouldn't cut it off.
        'welcomeGreetingInterruptible="dtmf">'
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


@router.post("/amd")
async def amd_result(request: Request, candidate_id: int, reason: str = "follow_up", s: Session = Depends(get_session)):
    """Async answering-machine detection result. The agent is already talking; if it's a voicemail,
    swap the call over to leaving our voicemail message."""
    form = await _verified_form(request)
    answered_by = form.get("AnsweredBy", "")
    c = s.get(Candidate, candidate_id)
    if c and (answered_by.startswith("machine") or answered_by == "fax"):
        text, en = template("voicemail", c.preferred_language, first_name=c.first_name)
        _log_spoken(s, c, text, en)
        log_event(s, c, "voicemail_left", Actor.system, reason=reason)
        _text_after_missed_call(s, c)
        s.commit()
        vr = VoiceResponse()
        vr.pause(length=1)
        vr.say(text, voice=VOICES.get(c.preferred_language, VOICES["en"])[0])
        vr.hangup()
        try:
            await asyncio.to_thread(lambda: telephony.client().calls(form.get("CallSid")).update(twiml=str(vr)))
        except Exception:
            log.exception("could not switch call to voicemail")
    return Response(status_code=204)


def _text_after_missed_call(s: Session, c: Candidate) -> None:
    """Same-day rule: a call replaces that day's text; if the call isn't answered, send the text."""
    from ..conversation import send
    body, en = template("call_fallback", c.preferred_language, first_name=c.first_name)
    send(s, c, body, en, Sender.system, c.preferred_channel if c.preferred_channel != Channel.voice else Channel.sms)


@router.post("/relay-ended")
async def relay_ended(request: Request, candidate_id: int, s: Session = Depends(get_session)):
    """Twilio calls this when the AI conversation ends: log how it ended and how long it lasted."""
    form = await _verified_form(request)
    c = s.get(Candidate, candidate_id)
    if c:
        log_event(s, c, "call_ended", Actor.system, call_sid=form.get("CallSid"),
                  status=form.get("SessionStatus"), duration_s=form.get("SessionDuration"),
                  error=form.get("ErrorMessage"))
        s.commit()
    vr = VoiceResponse()
    vr.hangup()
    return _xml(str(vr))


def _discard_replies(ids: list[int]) -> None:
    """Remove a superseded turn (its partial speech + the reply that was never spoken); the merged turn replaces it."""
    with Session(engine) as s:
        for m in s.exec(select(Message).where(Message.id.in_(ids))).all():
            s.delete(m)
        s.commit()


def _process_turn(candidate_id: int, speech: str, lang: str | None) -> tuple[str, bool, str, list[int]]:
    """Run one caller turn through the shared conversation logic.
    Returns (text to speak, end call?, reply language, ids of the messages this turn created)."""
    with Session(engine) as s:
        c = s.get(Candidate, candidate_id)
        low = speech.lower()
        if any(w in low for w in LATER_WORDS) and len(low.split()) <= 8:
            s.add(Message(candidate_id=c.id, direction="in", channel=Channel.voice, sender=Sender.candidate, body=speech))
            text, en = template("voice_later", c.preferred_language)
            _log_spoken(s, c, text, en); s.commit()
            return text, True, c.preferred_language, []

        last_id = s.exec(select(Message.id).where(Message.candidate_id == c.id).order_by(Message.id.desc())).first() or 0
        stage_before = c.stage
        handle_inbound(s, c, speech, Channel.voice)  # same brain as SMS: code decides, Claude writes
        said_goodbye = s.info.get("last_intent") == "goodbye"
        s.refresh(c)
        new_msgs = s.exec(select(Message).where(Message.candidate_id == c.id, Message.id > last_id)
                          .order_by(Message.id)).all()
        # Speak only what was meant for the call. Anything sent by text this turn (e.g. a link for the
        # next step) gets a short spoken heads-up instead of being read aloud.
        replies = [m for m in new_msgs if m.direction == "out" and m.channel == Channel.voice]
        texted_link = any(m.direction == "out" and m.channel != Channel.voice and "http" in m.body for m in new_msgs)
        text = " ".join(m.body for m in replies)
        if texted_link:
            text = f"{text} {template('voice_link_texted', c.preferred_language)[0]}".strip()
        text = text or template("voice_no_input", c.preferred_language)[0]
        over = (stage_before == Stage.screening and c.stage != Stage.screening) \
            or c.status == CandidateStatus.needs_review or said_goodbye
        if over:
            text = f"{text} {template('voice_goodbye', c.preferred_language)[0]}"
        return text, over, c.preferred_language, [m.id for m in new_msgs]


MERGE_WAIT_S = 0.5  # after a turn, wait this long for more speech before replying


@router.websocket("/relay")
async def relay(ws: WebSocket, token: str):
    candidate_id = _call_tokens.pop(token, None)
    if candidate_id is None:
        await ws.close(code=1008)
        return
    await ws.accept()
    log.info("ConversationRelay connected for candidate %s", candidate_id)

    pending: list[str] = []       # caller speech not yet answered
    new_speech = asyncio.Event()  # set whenever another turn arrives
    loop = asyncio.get_running_loop()
    last_heard = [0.0]
    done = asyncio.Event()

    async def responder() -> None:
        """Waits for a quiet moment, then answers everything said since the last reply.
        If the caller keeps talking while we prepare a reply, that reply is discarded and we
        answer the combined speech instead (fixes 'answered only the first half')."""
        while not done.is_set():
            await new_speech.wait()
            new_speech.clear()
            while loop.time() - last_heard[0] < MERGE_WAIT_S:  # debounce: let them finish
                await asyncio.sleep(0.1)
            if not pending:
                continue
            speech = " ".join(pending)
            pending.clear()
            text, end, reply_lang, reply_ids = await asyncio.to_thread(_process_turn, candidate_id, speech, None)
            if pending:  # they kept talking while we were thinking: drop this reply, answer it all together
                await asyncio.to_thread(_discard_replies, reply_ids)
                pending.insert(0, speech)
                new_speech.set()
                continue
            tts_lang = RELAY_VOICES.get(reply_lang, RELAY_VOICES["en"])[0]
            # lang picks the matching <Language> voice (native Spanish voice for Spanish replies).
            await ws.send_text(json.dumps({"type": "text", "token": text, "last": True, "lang": tts_lang}))
            if end:
                await asyncio.sleep(min(2 + len(text) / 14, 20))  # let the voice finish first
                await ws.send_text(json.dumps({"type": "end"}))
                done.set()

    task = asyncio.create_task(responder())
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            kind = msg.get("type")
            if kind == "prompt" and msg.get("last", True):
                speech = (msg.get("voicePrompt") or "").strip()
                if speech:
                    pending.append(speech)
                    last_heard[0] = loop.time()
                    new_speech.set()
            elif kind == "interrupt":
                await asyncio.to_thread(_log_interrupt, candidate_id, msg)
            elif kind == "error":
                log.warning("ConversationRelay error: %s", msg.get("description"))
    except WebSocketDisconnect:
        log.info("ConversationRelay disconnected for candidate %s", candidate_id)
    finally:
        done.set()
        task.cancel()


def _log_interrupt(candidate_id: int, msg: dict) -> None:
    with Session(engine) as s:
        c = s.get(Candidate, candidate_id)
        log_event(s, c, "caller_interrupted", Actor.candidate,
                  after_ms=msg.get("durationUntilInterruptMs"), heard=msg.get("utteranceUntilInterrupt"))
        s.commit()

"""Voice calls, turn-based (DESIGN.md: voice option A).

Twilio does speech-to-text and text-to-speech. Each time the candidate finishes speaking,
Twilio posts the transcript here; we run the SAME conversation logic as SMS
(conversation.handle_inbound) and speak back whatever it decided to send.
Streaming (ConversationRelay) will replace this transport later; the logic stays the same.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlmodel import Session, select
from twilio.twiml.voice_response import Gather, VoiceResponse

from .. import telephony
from ..config import VOICES
from ..conversation import handle_inbound, log_event, template
from ..db import get_session
from ..models import Actor, Candidate, CandidateStatus, Channel, Message, Sender, Stage

log = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice (Twilio webhooks)"])

SPANISH_WORDS = ("español", "espanol", "spanish")
ENGLISH_WORDS = ("english", "inglés", "ingles")
LATER_WORDS = ("not now", "later", "busy", "no tengo tiempo", "ahora no", "más tarde", "mas tarde", "ocupad")


async def _verified_form(request: Request) -> dict:
    form = dict(await request.form())
    if telephony.twilio_ready() and telephony.PUBLIC_URL:
        url = telephony.PUBLIC_URL + request.url.path + (f"?{request.url.query}" if request.url.query else "")
        if not telephony.valid_signature(url, form, request.headers.get("X-Twilio-Signature", "")):
            raise HTTPException(403, "Invalid Twilio signature")
    return form


def _twiml(vr: VoiceResponse) -> Response:
    return Response(content=str(vr), media_type="application/xml")


def _voice(lang: str) -> tuple[str, str]:
    return VOICES.get(lang, VOICES["en"])


def _say_and_listen(vr: VoiceResponse, c: Candidate, text: str) -> None:
    voice, speech_lang = _voice(c.preferred_language)
    g = Gather(input="speech", speech_timeout="auto", language=speech_lang,
               action=f"/voice/turn?candidate_id={c.id}", action_on_empty_result=True, method="POST")
    g.say(text, voice=voice)
    vr.append(g)


def _log_spoken(s: Session, c: Candidate, text: str, en: str, sender: Sender = Sender.system) -> None:
    s.add(Message(candidate_id=c.id, direction="out", channel=Channel.voice, sender=sender, body=text,
                  language=c.preferred_language, translation_en=en if en != text else None))


def _open_call(s: Session, c: Candidate, greeting_key: str) -> Response:
    vr = VoiceResponse()
    if c.stage != Stage.screening or c.status in (CandidateStatus.needs_review, CandidateStatus.rejected, CandidateStatus.dropped):
        text, en = template("voice_later", c.preferred_language)  # nothing to do by voice at this stage yet
        _log_spoken(s, c, text, en)
        vr.say(text, voice=_voice(c.preferred_language)[0])
        vr.hangup()
    else:
        text, en = template(greeting_key, c.preferred_language, first_name=c.first_name)
        _log_spoken(s, c, text, en)
        _say_and_listen(vr, c, text)
    s.commit()
    return _twiml(vr)


@router.post("/inbound")
async def inbound(request: Request, s: Session = Depends(get_session)):
    """Candidate calls our number."""
    form = await _verified_form(request)
    caller = form.get("From", "")
    c = s.exec(select(Candidate).where(Candidate.phone == caller).order_by(Candidate.created_at.desc())).first()
    if not c:
        vr = VoiceResponse()
        vr.say(template("voice_unknown_caller", "en")[0], voice=_voice("en")[0])
        vr.hangup()
        return _twiml(vr)
    log_event(s, c, "call_inbound", Actor.candidate, call_sid=form.get("CallSid"))
    return _open_call(s, c, "voice_inbound_greeting")


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
        vr = VoiceResponse()
        vr.say(text, voice=_voice(c.preferred_language)[0])
        vr.hangup()
        return _twiml(vr)
    log_event(s, c, "call_answered", Actor.candidate, reason=reason, call_sid=form.get("CallSid"))
    return _open_call(s, c, "voice_greeting")


@router.post("/turn")
async def turn(request: Request, candidate_id: int, retry: int = 0, s: Session = Depends(get_session)):
    """Candidate finished speaking. Same brain as SMS."""
    form = await _verified_form(request)
    c = s.get(Candidate, candidate_id)
    speech = (form.get("SpeechResult") or "").strip()
    vr = VoiceResponse()

    if not speech:
        if retry >= 1:
            text, en = template("voice_later", c.preferred_language)
            _log_spoken(s, c, text, en); s.commit()
            vr.say(text, voice=_voice(c.preferred_language)[0]); vr.hangup()
            return _twiml(vr)
        text, _ = template("voice_no_input", c.preferred_language)
        voice, speech_lang = _voice(c.preferred_language)
        g = Gather(input="speech", speech_timeout="auto", language=speech_lang,
                   action=f"/voice/turn?candidate_id={c.id}&retry=1", action_on_empty_result=True, method="POST")
        g.say(text, voice=voice)
        vr.append(g)
        return _twiml(vr)

    low = speech.lower()
    # Language switch (speech recognition needs the language up front, so we switch explicitly).
    wants = "es" if any(w in low for w in SPANISH_WORDS) else "en" if any(w in low for w in ENGLISH_WORDS) else None
    if wants and wants != c.preferred_language and len(low.split()) <= 3:
        log_event(s, c, "language_changed", Actor.candidate, **{"from": c.preferred_language, "to": wants}, channel="voice")
        c.preferred_language = wants
        s.add(Message(candidate_id=c.id, direction="in", channel=Channel.voice, sender=Sender.candidate, body=speech))
        text, en = template("voice_greeting", wants, first_name=c.first_name)
        _log_spoken(s, c, text, en); s.commit()
        _say_and_listen(vr, c, text)
        return _twiml(vr)

    if any(w in low for w in LATER_WORDS) and len(low.split()) <= 6:
        s.add(Message(candidate_id=c.id, direction="in", channel=Channel.voice, sender=Sender.candidate, body=speech))
        text, en = template("voice_later", c.preferred_language)
        _log_spoken(s, c, text, en); s.commit()
        vr.say(text, voice=_voice(c.preferred_language)[0]); vr.hangup()
        return _twiml(vr)

    last_id = s.exec(select(Message.id).where(Message.candidate_id == c.id).order_by(Message.id.desc())).first() or 0
    handle_inbound(s, c, speech, Channel.voice)
    s.refresh(c)
    replies = s.exec(select(Message).where(Message.candidate_id == c.id, Message.direction == "out",
                                           Message.id > last_id).order_by(Message.id)).all()
    text = " ".join(m.body for m in replies) or template("voice_no_input", c.preferred_language)[0]

    screening_over = c.stage != Stage.screening or c.status == CandidateStatus.needs_review
    if screening_over:
        bye, _ = template("voice_goodbye", c.preferred_language)
        vr.say(f"{text} {bye}", voice=_voice(c.preferred_language)[0])
        vr.hangup()
    else:
        _say_and_listen(vr, c, text)
    return _twiml(vr)

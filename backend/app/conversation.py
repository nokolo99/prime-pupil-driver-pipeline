"""Candidate conversation: intake and screening.

The code here owns every decision: which question is next, when screening is complete,
whether answers trigger a knockout flag, and what happens next. Claude (ai.py) only reads
and writes the words.
"""

import logging
from typing import Optional

from sqlmodel import Session, select

from . import ai
from .config import KNOCKOUT_RULES, MAX_CLARIFY_ATTEMPTS, SCREENING_QUESTIONS, TEMPLATES
from .models import (
    Actor, Candidate, CandidateStatus, Channel, Event, Message, Recruiter, ScreeningResult,
    Sender, Stage, Step, StepResult, StepStatus, Task, now,
)

log = logging.getLogger(__name__)


# ---------- Small helpers ----------

def log_event(s: Session, candidate: Candidate, type_: str, actor: Actor, **details) -> None:
    s.add(Event(candidate_id=candidate.id, type=type_, actor=actor, details=details))


def create_task(s: Session, candidate: Candidate, type_: str, reason: str, priority: int = 2) -> None:
    s.add(Task(candidate_id=candidate.id, type=type_, reason=reason, priority=priority,
               assigned_recruiter_id=candidate.recruiter_id))
    log_event(s, candidate, "task_created", Actor.system, task_type=type_, reason=reason)


def template(key: str, lang: str, **kw) -> tuple[str, str]:
    """Returns (text in candidate's language, English version)."""
    en = TEMPLATES[key]["en"].format(**kw)
    if lang in TEMPLATES[key]:
        return TEMPLATES[key][lang].format(**kw), en
    try:
        return ai.translate(en, lang), en
    except Exception:
        log.exception("translation failed")
        return en, en


def send(s: Session, candidate: Candidate, body: str, body_en: Optional[str], sender: Sender,
         channel: Optional[Channel] = None) -> Message:
    """Record an outbound message. On a voice call the voice route speaks it; SMS delivery is plugged in later."""
    msg = Message(candidate_id=candidate.id, direction="out", channel=channel or candidate.preferred_channel,
                  sender=sender, body=body, language=candidate.preferred_language,
                  translation_en=body_en if body_en and body_en != body else None)
    s.add(msg)
    candidate.last_contacted_at = now()
    if msg.channel in (Channel.sms, Channel.whatsapp) and not candidate.opted_out:
        _deliver_sms(s, candidate, msg)
    return msg


def _deliver_sms(s: Session, candidate: Candidate, msg: Message) -> None:
    """Hand an outbound text to Twilio. Failures are logged on the timeline, never raised."""
    from . import telephony
    if not telephony.twilio_ready():
        return
    try:
        send_fn = telephony.send_whatsapp if msg.channel == Channel.whatsapp else telephony.send_sms
        msg.provider_id = send_fn(candidate.phone, msg.body)
    except Exception as e:
        log.warning("SMS to %s failed: %s", candidate.phone, e)
        s.add(Event(candidate_id=candidate.id, type="sms_failed", actor=Actor.system,
                    details={"error": str(getattr(e, "msg", e))[:200]}))


def screening_step(s: Session, candidate: Candidate) -> tuple[Step, ScreeningResult]:
    step = s.exec(select(Step).where(Step.candidate_id == candidate.id, Step.stage == Stage.screening)).one()
    return step, s.get(ScreeningResult, step.id)


def remaining_questions(sr: ScreeningResult) -> list[dict]:
    """Unanswered screening questions, in order. Code decides the order and what counts as done."""
    out = []
    for q in SCREENING_QUESTIONS:
        if f"Unclear answer: {q['field']}" in (sr.knockout_flags or []):
            continue  # flagged as unclear; recruiter will follow up
        if q["field"] == "years_licensed" and sr.has_valid_license is False:
            continue  # no license, so no years to ask about
        if getattr(sr, q["field"]) is None:
            out.append(q)
    return out


# ---------- Intake (Workday "new applicant" event) ----------

def intake_applicant(s: Session, *, first_name: str, last_name: str, phone: str, email: Optional[str],
                     depot_id: int, language: str, sms_consent: bool, workday_id: Optional[str],
                     channel: str = "sms") -> Candidate:
    if language not in ("en", "es"):
        language = "en"  # "Other": start in English; we switch as soon as they reply in their language
    recruiter = s.exec(select(Recruiter).where(Recruiter.depot_id == depot_id)).first() \
        or s.exec(select(Recruiter)).first()
    c = Candidate(first_name=first_name, last_name=last_name, phone=phone, email=email,
                  depot_id=depot_id, recruiter_id=recruiter.id if recruiter else None,
                  preferred_language=language, source="workday", workday_id=workday_id,
                  preferred_channel=Channel(channel) if channel in ("sms", "whatsapp") else Channel.sms,
                  stage=Stage.screening, status=CandidateStatus.waiting_on_candidate,
                  sms_consent_at=now() if sms_consent else None)
    s.add(c)
    s.flush()

    step = Step(candidate_id=c.id, stage=Stage.screening, status=StepStatus.waiting_on_candidate,
                started_at=now())
    s.add(step)
    s.flush()
    s.add(ScreeningResult(step_id=step.id))

    log_event(s, c, "applied", Actor.system, source="workday", workday_id=workday_id)

    if not sms_consent:
        create_task(s, c, "no_sms_consent", "Applied without SMS consent: contact by phone or email", priority=2)
    else:
        body, en = template("intro", language, first_name=first_name)
        send(s, c, body, en, Sender.system)
        log_event(s, c, "message_sent", Actor.system, kind="intro")
    s.commit()
    s.refresh(c)
    return c


# ---------- Inbound message ----------

def handle_inbound(s: Session, candidate: Candidate, body: str, channel: Channel) -> None:
    s.add(Message(candidate_id=candidate.id, direction="in", channel=channel, sender=Sender.candidate, body=body))
    candidate.last_reply_at = now()
    s.flush()

    if candidate.opted_out:
        s.commit()
        return

    if candidate.stage in ASSISTED_STAGES and candidate.status != CandidateStatus.needs_review:
        _handle_stage_turn(s, candidate, body, channel)
        s.commit()
        return

    if candidate.stage != Stage.screening or candidate.status == CandidateStatus.needs_review:
        # Under review, or a stage the assistant doesn't cover yet: route to a recruiter.
        create_task(s, candidate, "candidate_message", f"Candidate replied: “{body[:80]}”", priority=3)
        s.commit()
        return

    _handle_screening_turn(s, candidate, body, channel)
    s.commit()


def _transcript(s: Session, candidate: Candidate) -> list[tuple[str, str]]:
    msgs = s.exec(select(Message).where(Message.candidate_id == candidate.id).order_by(Message.created_at)).all()
    return [("Candidate" if m.direction == "in" else "Assistant", m.body) for m in msgs[:-1]]


def _handle_screening_turn(s: Session, c: Candidate, body: str, channel: Channel = Channel.web) -> None:
    step, sr = screening_step(s, c)
    step.nudge_count, step.last_nudged_at = 0, None  # candidate is active again: restart follow-ups
    remaining = remaining_questions(sr)
    answered = {f["field"]: getattr(sr, f["field"]) for f in SCREENING_QUESTIONS if getattr(sr, f["field"]) is not None}

    try:
        turn = ai.run_turn(first_name=c.first_name, language=c.preferred_language,
                           remaining_questions=[q["ask"] for q in remaining], answered=answered,
                           voice=(channel == Channel.voice),
                           transcript=_transcript(s, c), latest=body)
    except Exception as e:
        log.exception("Claude turn failed")
        log_event(s, c, "ai_error", Actor.ai, error=str(e)[:200])
        text, en = template("error", c.preferred_language)
        send(s, c, text, en, Sender.system, channel)
        return

    # Store translation of the inbound message for recruiters.
    inbound = s.exec(select(Message).where(Message.candidate_id == c.id, Message.direction == "in")
                     .order_by(Message.created_at.desc())).first()
    inbound.language = turn.language
    if turn.candidate_message_en.strip() != body.strip():
        inbound.translation_en = turn.candidate_message_en

    # Language switch: follow the candidate.
    if turn.language and turn.language != c.preferred_language:
        log_event(s, c, "language_changed", Actor.ai, **{"from": c.preferred_language, "to": turn.language})
        c.preferred_language = turn.language

    # Save extracted answers (code decides what to keep).
    newly = {k: v for k, v in turn.extracted.model_dump().items() if v is not None}
    for k, v in newly.items():
        setattr(sr, k, v)
    if newly:
        log_event(s, c, "screening_answer", Actor.ai, answers=newly)

    # Unclear answers: allow N clarifications, then flag for a recruiter.
    if turn.intent == "unclear" and turn.unclear_field:
        counts = dict(sr.unclear_counts or {})
        counts[turn.unclear_field] = counts.get(turn.unclear_field, 0) + 1
        sr.unclear_counts = counts
        if counts[turn.unclear_field] > MAX_CLARIFY_ATTEMPTS:
            sr.knockout_flags = list(sr.knockout_flags or []) + [f"Unclear answer: {turn.unclear_field}"]
            log_event(s, c, "answer_flagged_unclear", Actor.system, field=turn.unclear_field)

    if turn.intent in ("question_handoff", "wants_human"):
        reason = "Asked to talk to a person" if turn.intent == "wants_human" else f"Question for recruiter: “{turn.candidate_message_en[:100]}”"
        create_task(s, c, "candidate_question", reason, priority=2)

    # Is screening complete? (code decides)
    if not remaining_questions(sr):
        _finish_screening(s, c, step, sr, channel)
        return

    send(s, c, turn.reply, turn.reply_en, Sender.ai, channel)
    log_event(s, c, "message_sent", Actor.ai, intent=turn.intent)


def _finish_screening(s: Session, c: Candidate, step: Step, sr: ScreeningResult, channel: Channel = Channel.web) -> None:
    flags = [label for field, check, label in KNOCKOUT_RULES if check(getattr(sr, field))]
    flags += [f for f in (sr.knockout_flags or []) if f.startswith("Unclear answer")]
    sr.knockout_flags = flags
    step.completed_at = now()

    if flags:
        step.status, step.result = StepStatus.passed, StepResult.flag  # completed, but needs a human
        c.status = CandidateStatus.needs_review
        create_task(s, c, "review_knockout", "Screening flags: " + "; ".join(flags), priority=1)
        text, en = template("screening_review", c.preferred_language)
        log_event(s, c, "screening_completed", Actor.system, result="flag", flags=flags)
    else:
        step.status, step.result = StepStatus.passed, StepResult.pass_
        text, en = template("screening_passed", c.preferred_language)
        log_event(s, c, "screening_completed", Actor.system, result="pass")

    send(s, c, text, en, Sender.system, channel)
    if not flags:
        from .stages import advance  # lazy: stages imports this module
        advance(s, c, Stage.background_check)



# ---------- After screening: stage-aware help ----------

ASSISTED_STAGES = (Stage.background_check, Stage.drug_test, Stage.cdl_permit, Stage.training, Stage.skills_test, Stage.offer)


def step_facts(s: Session, c: Candidate) -> dict:
    """What the assistant may tell the candidate about their current step."""
    from .models import BackgroundCheck, Clinic, DrugTest
    from .stages import current_step, fmt_when, nearby_clinics
    step = current_step(s, c)
    if c.stage == Stage.background_check:
        bc = s.get(BackgroundCheck, step.id)
        return {"what": "Background check and driving record (DOT). Candidate fills out the vendor's online form; "
                        "results usually take 3-5 days after the form is submitted.",
                "form_link": bc.form_link, "form_submitted": bool(bc.form_completed_at),
                "status": "waiting on vendor results" if bc.form_completed_at else "waiting for candidate to fill out the form"}
    if c.stage == Stage.drug_test:
        dt = s.get(DrugTest, step.id)
        clinic = s.get(Clinic, dt.clinic_id) if dt.clinic_id else None
        return {"what": "DOT drug test (urine) at a clinic in the vendor's network. Takes about 15 minutes. "
                        "Bring a government photo ID. Results usually take 2-5 days.",
                "booking_link": dt.booking_link,
                "nearby_clinics": [f"{cl.name}, {cl.address} ({cl.hours})" for cl in nearby_clinics(s, c)],
                "appointment": f"{clinic.name}, {fmt_when(dt.appointment_at)}" if dt.appointment_at else None,
                "sample_collected": bool(dt.collected_at)}
    from .config import DMV_PERMIT_LINK
    from .models import Offer, PermitCheck, SkillsTest, Training
    if c.stage == Stage.cdl_permit:
        pc = s.get(PermitCheck, step.id)
        return {"what": "CDL learner's permit (Class B). Candidate books and takes the written knowledge test at the DMV, "
                        "then texts us a photo of the permit. Bring ID and proof of residency to the DMV; a small DMV fee applies.",
                "dmv_link": DMV_PERMIT_LINK, "photo_received": bool(pc and pc.received_at),
                "how_to_send_proof": "Text a clear photo of the front of the permit to this number."}
    if c.stage == Stage.training:
        tr = s.get(Training, step.id)
        return {"what": "Paid CDL training over Zoom, about 1 week. Paid at the training rate in the facts.",
                "starts": fmt_when(tr.cohort_start), "zoom_link": tr.session_link}
    if c.stage == Stage.skills_test:
        st = s.get(SkillsTest, step.id)
        return {"what": "CDL skills assessment on an online platform; results come to Prime Pupil automatically.",
                "test_link": st.test_link, "attempt": st.attempts}
    if c.stage == Stage.offer:
        o = s.get(Offer, step.id)
        return {"what": "Job offer, signed electronically.", "sign_link": o.sign_link, "terms": o.terms}
    return {}


def _handle_stage_turn(s: Session, c: Candidate, body: str, channel: Channel) -> None:
    from .stages import current_step
    step = current_step(s, c)
    try:
        turn = ai.run_stage_turn(first_name=c.first_name, language=c.preferred_language, stage=c.stage.value,
                                 step_facts=step_facts(s, c), transcript=_transcript(s, c), latest=body,
                                 voice=(channel == Channel.voice))
    except Exception as e:
        log.exception("Claude stage turn failed")
        log_event(s, c, "ai_error", Actor.ai, error=str(e)[:200])
        text, en = template("error", c.preferred_language)
        send(s, c, text, en, Sender.system, channel)
        return

    inbound = s.exec(select(Message).where(Message.candidate_id == c.id, Message.direction == "in")
                     .order_by(Message.created_at.desc())).first()
    inbound.language = turn.language
    if turn.candidate_message_en.strip() != body.strip():
        inbound.translation_en = turn.candidate_message_en
    if turn.language and turn.language != c.preferred_language:
        log_event(s, c, "language_changed", Actor.ai, **{"from": c.preferred_language, "to": turn.language})
        c.preferred_language = turn.language

    # Candidate is engaged: restart follow-ups (but never trust "I already did it"; the vendor confirms).
    step.nudge_count, step.last_nudged_at = 0, None
    if turn.intent == "question_handoff":
        create_task(s, c, "candidate_question", f"Question for recruiter: “{turn.candidate_message_en[:100]}”", priority=2)
    elif turn.intent == "wants_to_withdraw":
        create_task(s, c, "candidate_withdrawing", f"Candidate may withdraw: “{turn.candidate_message_en[:100]}”", priority=1)
    elif turn.intent == "claims_done":
        log_event(s, c, "candidate_claims_done", Actor.candidate, stage=c.stage.value)

    send(s, c, turn.reply, turn.reply_en, Sender.ai, channel)
    log_event(s, c, "message_sent", Actor.ai, intent=turn.intent, stage=c.stage.value)
    s.info["last_intent"] = turn.intent  # lets the voice route end the call on "goodbye"

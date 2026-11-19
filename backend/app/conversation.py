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


def send(s: Session, candidate: Candidate, body: str, body_en: Optional[str], sender: Sender) -> Message:
    """Record an outbound message. Delivery (SMS / voice) is plugged in later; the simulator reads these rows."""
    msg = Message(candidate_id=candidate.id, direction="out", channel=candidate.preferred_channel,
                  sender=sender, body=body, language=candidate.preferred_language,
                  translation_en=body_en if body_en and body_en != body else None)
    s.add(msg)
    candidate.last_contacted_at = now()
    return msg


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
                     depot_id: int, language: str, sms_consent: bool, workday_id: Optional[str]) -> Candidate:
    if language not in ("en", "es"):
        language = "en"  # "Other": start in English; we switch as soon as they reply in their language
    recruiter = s.exec(select(Recruiter).where(Recruiter.depot_id == depot_id)).first() \
        or s.exec(select(Recruiter)).first()
    c = Candidate(first_name=first_name, last_name=last_name, phone=phone, email=email,
                  depot_id=depot_id, recruiter_id=recruiter.id if recruiter else None,
                  preferred_language=language, source="workday", workday_id=workday_id,
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

    if candidate.stage != Stage.screening or candidate.status == CandidateStatus.needs_review:
        # Later stages are handled in later increments. For now, route to a recruiter.
        create_task(s, candidate, "candidate_message", f"Candidate replied: “{body[:80]}”", priority=3)
        s.commit()
        return

    _handle_screening_turn(s, candidate, body)
    s.commit()


def _transcript(s: Session, candidate: Candidate) -> list[tuple[str, str]]:
    msgs = s.exec(select(Message).where(Message.candidate_id == candidate.id).order_by(Message.created_at)).all()
    return [("Candidate" if m.direction == "in" else "Assistant", m.body) for m in msgs[:-1]]


def _handle_screening_turn(s: Session, c: Candidate, body: str) -> None:
    step, sr = screening_step(s, c)
    remaining = remaining_questions(sr)
    answered = {f["field"]: getattr(sr, f["field"]) for f in SCREENING_QUESTIONS if getattr(sr, f["field"]) is not None}

    try:
        turn = ai.run_turn(first_name=c.first_name, language=c.preferred_language,
                           remaining_questions=[q["ask"] for q in remaining], answered=answered,
                           transcript=_transcript(s, c), latest=body)
    except Exception as e:
        log.exception("Claude turn failed")
        log_event(s, c, "ai_error", Actor.ai, error=str(e)[:200])
        text, en = template("error", c.preferred_language)
        send(s, c, text, en, Sender.system)
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
        _finish_screening(s, c, step, sr)
        return

    send(s, c, turn.reply, turn.reply_en, Sender.ai)
    log_event(s, c, "message_sent", Actor.ai, intent=turn.intent)


def _finish_screening(s: Session, c: Candidate, step: Step, sr: ScreeningResult) -> None:
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
        _advance(s, c, Stage.background_check)

    send(s, c, text, en, Sender.system)


def _advance(s: Session, c: Candidate, to: Stage) -> None:
    log_event(s, c, "stage_changed", Actor.system, **{"from": c.stage.value, "to": to.value})
    c.stage, c.stage_entered_at = to, now()
    s.add(Step(candidate_id=c.id, stage=to, status=StepStatus.not_started))
    # The background-check flow (vendor order, form link, nudges) arrives in increment 4.
    c.status = CandidateStatus.waiting_on_vendor

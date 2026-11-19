"""The only place that talks to Claude.

Design rule (DESIGN.md §9): code decides, Claude writes. Claude is told which question to ask,
reads the candidate's reply, and returns structured data. It never sees the knockout rules
and cannot advance, reject, or flag anyone.
"""

import json
import logging
from typing import Literal, Optional

import anthropic
from pydantic import BaseModel, Field

from .config import CLAUDE_MODEL, CLAUDE_MODEL_VOICE, FACTS

log = logging.getLogger(__name__)
client = anthropic.Anthropic()


class Extracted(BaseModel):
    """Screening answers found in the candidate's latest message. Null = not answered."""
    is_21_plus: Optional[bool] = None
    has_valid_license: Optional[bool] = None
    years_licensed: Optional[float] = None
    recent_violations: Optional[bool] = None
    violations_note: Optional[str] = None
    availability_ok: Optional[bool] = None
    has_cdl_or_permit: Optional[bool] = None


class TurnResult(BaseModel):
    intent: Literal[
        "answered",          # answered one or more screening questions
        "unclear",           # tried to answer, but the answer is ambiguous
        "question_answered", # asked something the facts sheet covers (answered in reply)
        "question_handoff",  # asked something the facts sheet does NOT cover
        "wants_human",       # asked for a person
        "other",             # greeting, "yes I have 5 minutes", small talk
    ]
    extracted: Extracted
    unclear_field: Optional[str] = Field(None, description="Which field was unclear, if intent=unclear")
    language: str = Field(description="ISO 639-1 code of the language the candidate wrote in, e.g. en, es")
    candidate_message_en: str = Field(description="English translation of the candidate's latest message (copy it if already English)")
    reply: str = Field(description="Your SMS reply, in the candidate's language")
    reply_en: str = Field(description="English translation of your reply (copy it if already English)")


SYSTEM = f"""You are the SMS recruiting assistant for Prime Pupil Transportation, a school bus company hiring drivers.

You talk with candidates, many of whom are hourly workers, career changers, or retirees texting from an older phone between shifts.

How you work:
- The system gives you the remaining screening questions, in order. After extracting answers from the latest message, ask the FIRST remaining question that this message did not answer. Ask only one question per reply. Keep the meaning of the question exactly (same time window, same criteria); you may phrase it naturally in the candidate's language.
- Never decide whether the candidate qualifies, and never tell them they passed, failed, or are disqualified.
- Read the candidate's latest message and extract any screening answers into `extracted`. Only fill a field when the candidate clearly answered it. Convert natural answers ("como 3 años" -> years_licensed 3, "nope never" -> recent_violations false).
- Before asking the next question, briefly confirm back what they told you ("Got it, 3 years.").
- If an answer is ambiguous, set intent "unclear", name the field in `unclear_field`, and ask one short clarifying question instead of moving on.
- If the latest message answers every remaining question, do not ask anything; just thank them in one short sentence (the system sends the next step).
- If they ask a question, answer ONLY from the facts below. If the facts don't cover it, set intent "question_handoff" and do not guess. If they ask for a person, set intent "wants_human".
- Reply in the language the candidate is writing in. Plain, warm, short: aim for under 160 characters, one ask per message. No emojis, no markdown.

Facts you may use:
{FACTS}"""


VOICE_NOTE = """

This turn is a live phone call: your reply will be spoken aloud. Keep it to one or two short sentences, conversational, no lists or symbols."""


def _call(model: str, **kw):
    """Structured-output call. Server-side refusal fallback where the model supports it (not Haiku)."""
    if "haiku" in model:
        return client.messages.parse(model=model, **kw)
    return client.beta.messages.parse(model=model, betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kw)


def run_turn(*, first_name: str, language: str, remaining_questions: list[str],
             answered: dict, transcript: list[tuple[str, str]], latest: str, voice: bool = False) -> TurnResult:
    """One Claude call per inbound message. Raises on API failure; the caller handles fallback."""
    history = "\n".join(f"{who}: {text}" for who, text in transcript[-20:])
    state = {
        "candidate_first_name": first_name,
        "preferred_language": language,
        "already_answered": answered,
        "remaining_questions_in_order": remaining_questions,
    }
    user = (
        f"Current state:\n{json.dumps(state, ensure_ascii=False)}\n\n"
        f"Conversation so far:\n{history}\n\n"
        f"Candidate's latest message:\n{latest}"
    )
    resp = _call(
        CLAUDE_MODEL_VOICE if voice else CLAUDE_MODEL,
        max_tokens=2000,
        output_config={"effort": "low"},
        system=SYSTEM + (VOICE_NOTE if voice else ""),
        messages=[{"role": "user", "content": user}],
        output_format=TurnResult,
    )
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        raise RuntimeError(f"No usable output (stop_reason={resp.stop_reason})")
    return resp.parsed_output


class Translation(BaseModel):
    text: str


def translate(text: str, to_language: str) -> str:
    """Translate a fixed template into a language we don't have a template for."""
    resp = _call(
        CLAUDE_MODEL,
        max_tokens=1000,
        output_config={"effort": "low"},
        system="Translate the SMS message faithfully. Keep it short and plain. Do not add anything.",
        messages=[{"role": "user", "content": f"Target language (ISO 639-1): {to_language}\n\n{text}"}],
        output_format=Translation,
    )
    return resp.parsed_output.text if resp.parsed_output else text

"""Recruiter-editable settings (DESIGN.md: recruiter settings A-D).

Defaults live in config.py. The Settings page saves only overrides (one JSON row in the Setting
table), so "reset to default" is always possible. Everything that used to read a constant now
reads through these getters, so changes take effect on the next message / engine tick.
"""

import json
import re
from typing import Any

from sqlmodel import Session

from . import config

_cache: dict | None = None
SETTINGS_KEY = "recruiter_settings"

EDITABLE_STAGES = ["screening", "background_check", "drug_test", "cdl_permit", "skills_test", "offer"]
SLA_STAGES = ["screening", "background_check", "drug_test", "cdl_permit", "training", "skills_test", "offer"]

# Templates recruiters can edit (internal/voice-plumbing ones stay in code).
EDITABLE_TEMPLATES = {
    "intro": "First message after applying", "screening_passed": "Passed screening", "screening_review": "Screening needs review",
    "reminder_1": "Generic reminder (early)", "reminder_2": "Generic reminder (middle)", "reminder_3": "Generic reminder (late)",
    "call_fallback": "Text when a call couldn't be placed", "bg_start": "Background check: form link",
    "bg_reminder": "Background check: reminder", "bg_form_received": "Background check: form received",
    "bg_clear": "Background check: clear", "under_review": "Results under recruiter review",
    "drug_start": "Drug test: booking link + clinics", "drug_reminder": "Drug test: reminder", "drug_booked": "Drug test: booked",
    "drug_day_before": "Drug test: day before", "drug_morning_of": "Drug test: morning of", "drug_no_show": "Drug test: missed appointment",
    "drug_collected": "Drug test: sample collected", "drug_negative": "Drug test: passed",
    "training_start": "Training: enrolled", "training_day_before": "Training: day before", "training_morning_of": "Training: morning of",
    "permit_start": "CDL permit: start (during training)", "permit_reminder": "CDL permit: reminder",
    "permit_photo_request": "CDL permit: photo before offer", "permit_received": "CDL permit: photo received",
    "permit_new_photo": "CDL permit: new photo needed", "skills_start": "Skills test: link", "skills_reminder": "Skills test: reminder",
    "skills_retest": "Skills test: retest allowed", "offer_start": "Offer: sent", "offer_reminder": "Offer: reminder",
    "hired": "Hired", "rejected": "Rejected (after recruiter decision)",
}


def defaults() -> dict:
    return {
        "follow_up": {st: [list(x) for x in config.FOLLOW_UP_SCHEDULE.get(st, config.DEFAULT_FOLLOW_UP)] for st in EDITABLE_STAGES},
        "give_up_after_days": config.GIVE_UP_AFTER_DAYS,
        "quiet_hours": list(config.QUIET_HOURS),
        "ai_calls_enabled": True,
        "templates": {k: dict(config.TEMPLATES[k]) for k in EDITABLE_TEMPLATES if k in config.TEMPLATES},
        "screening": {"min_age": 21, "min_years_licensed": config.MIN_YEARS_LICENSED, "dui_lookback_years": 7},
        "stage_sla_days": {st: config.STAGE_SLA_DAYS.get(st, 7) for st in SLA_STAGES},
        "results_overdue_days": dict(config.RESULTS_OVERDUE_DAYS),
    }


def _load_overrides() -> dict:
    global _cache
    if _cache is None:
        from .db import engine
        from .models import Setting
        with Session(engine) as s:
            row = s.get(Setting, SETTINGS_KEY)
            _cache = json.loads(row.value) if row else {}
    return _cache


def _merge(base: Any, over: Any) -> Any:
    if isinstance(base, dict) and isinstance(over, dict):
        return {k: _merge(base.get(k), over.get(k)) for k in {**base, **over}}
    return over if over is not None else base


def current() -> dict:
    return _merge(defaults(), _load_overrides())


def save_overrides(s: Session, overrides: dict) -> None:
    global _cache
    from .models import Setting
    row = s.get(Setting, SETTINGS_KEY) or Setting(key=SETTINGS_KEY, value="{}")
    row.value = json.dumps(overrides)
    s.add(row)
    s.commit()
    _cache = overrides


def overrides() -> dict:
    return _load_overrides()


# ---------- Getters used by the rest of the system ----------

def follow_up_schedule(stage: str) -> list[tuple[int, str]]:
    sched = current()["follow_up"].get(stage) or [list(x) for x in config.DEFAULT_FOLLOW_UP]
    return [(int(d), k) for d, k in sched]


def give_up_after_days() -> int:
    return int(current()["give_up_after_days"])


def quiet_hours() -> tuple[int, int]:
    a, b = current()["quiet_hours"]
    return int(a), int(b)


def ai_calls_enabled() -> bool:
    return bool(current()["ai_calls_enabled"])


def template_text(key: str, lang: str) -> str | None:
    t = current()["templates"].get(key) or config.TEMPLATES.get(key)
    return (t or {}).get(lang) if t else None


def template_langs(key: str) -> dict:
    return current()["templates"].get(key) or config.TEMPLATES.get(key, {})


def screening_questions() -> list[dict]:
    sc = current()["screening"]
    return [
        {"field": "is_21_plus", "ask": f"Are you {sc['min_age']} or older?"},
        {"field": "years_licensed", "ask": "How many years have you had your driver's license?"},
        {"field": "dui_past_7_years", "ask": f"Have you had a DUI in the past {sc['dui_lookback_years']} years?"},
        {"field": "willing_drug_test", "ask": "Are you willing to take a DOT drug test?"},
    ]


def knockout_rules() -> list:
    sc = current()["screening"]
    return [
        ("is_21_plus", lambda v: v is False, f"Under {sc['min_age']}"),
        ("years_licensed", lambda v, m=sc["min_years_licensed"]: v is not None and v < m, f"Licensed under {sc['min_years_licensed']} years"),
        ("dui_past_7_years", lambda v: v is True, f"DUI in the past {sc['dui_lookback_years']} years"),
        ("willing_drug_test", lambda v: v is False, "Not willing to take a drug test"),
    ]


def stage_sla_days() -> dict:
    return current()["stage_sla_days"]


def results_overdue_days() -> dict:
    return current()["results_overdue_days"]


# ---------- Validation (guardrails) ----------

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def validate(proposed: dict) -> list[str]:
    """Returns a list of human-readable problems; empty means OK to save."""
    errs = []
    d = defaults()
    for key, langs in (proposed.get("templates") or {}).items():
        if key not in d["templates"]:
            errs.append(f"Unknown message: {key}")
            continue
        for lang, text in langs.items():
            need = set(_PLACEHOLDER.findall(d["templates"][key].get(lang, d["templates"][key].get("en", ""))))
            have = set(_PLACEHOLDER.findall(text or ""))
            label = f"{EDITABLE_TEMPLATES.get(key, key)} ({lang.upper()})"
            if not (text or "").strip():
                errs.append(f"{label}: message can't be empty")
            if missing := need - have:
                errs.append(f"{label}: must keep " + ", ".join("{" + m + "}" for m in sorted(missing)))
            if extra := have - need:
                errs.append(f"{label}: unknown placeholder " + ", ".join("{" + x + "}" for x in sorted(extra)))
            if "STOP" in d["templates"][key].get(lang, "") and "STOP" not in (text or ""):
                errs.append(f"{label}: must keep the opt-out instruction (STOP); carriers require it for SMS")
    for stage, sched in (proposed.get("follow_up") or {}).items():
        days = [int(x[0]) for x in sched]
        if days != sorted(days) or len(set(days)) != len(days):
            errs.append(f"Follow-ups for {stage.replace('_', ' ')}: days must be increasing with no repeats")
        if any(x[1] not in ("sms", "call") for x in sched):
            errs.append(f"Follow-ups for {stage.replace('_', ' ')}: each step must be a text or a call")
        give_up = int(proposed.get("give_up_after_days", current()["give_up_after_days"]))
        if days and days[-1] >= give_up:
            errs.append(f"Follow-ups for {stage.replace('_', ' ')}: last reminder must be before day {give_up} (when reminders stop)")
    qh = proposed.get("quiet_hours")
    if qh and not all(0 <= int(h) <= 23 for h in qh):
        errs.append("Quiet hours must be between 0 and 23")
    sc = proposed.get("screening") or {}
    if "min_age" in sc and not 18 <= int(sc["min_age"]) <= 30:
        errs.append("Minimum age must be between 18 and 30")
    for k, v in (proposed.get("stage_sla_days") or {}).items():
        if int(v) < 1:
            errs.append(f"Time limit for {k.replace('_', ' ')} must be at least 1 day")
    return errs

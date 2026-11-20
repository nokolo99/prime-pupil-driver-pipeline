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
    "reminder_4": "Generic reminder (door's open)",
    **{f"{p}_reminder_{i}": f"{p} reminder v{i}" for p in ("bg", "drug", "permit", "skills", "offer") for i in (2, 3, 4)},
}

# How the Settings page groups messages. A ("reminders", stage) item opens that stage's rotating versions as tabs.
TEMPLATE_GROUPS = [
    {"group": "Screening", "items": [["intro", "First message after applying"], ["reminders", "screening"],
                                     ["screening_passed", "Passed screening"], ["screening_review", "Needs recruiter review"]]},
    {"group": "Background check", "items": [["bg_start", "Form link"], ["reminders", "background_check"], ["bg_form_received", "Form received"],
                                            ["bg_clear", "Result: clear"]]},
    {"group": "Drug test", "items": [["drug_start", "Booking link + clinics"], ["reminders", "drug_test"], ["drug_booked", "Booked"],
                                     ["drug_day_before", "Day before"], ["drug_morning_of", "Morning of"], ["drug_no_show", "Missed appointment"],
                                     ["drug_collected", "Sample collected"], ["drug_negative", "Passed"]]},
    {"group": "Training & CDL permit", "items": [["training_start", "Enrolled in training"], ["training_day_before", "Training: day before"],
                                                 ["training_morning_of", "Training: morning of"], ["permit_start", "Permit: start"],
                                                 ["reminders", "cdl_permit"], ["permit_photo_request", "Permit photo before offer"],
                                                 ["permit_received", "Permit photo received"], ["permit_new_photo", "New permit photo needed"]]},
    {"group": "Skills test", "items": [["skills_start", "Skills test link"], ["reminders", "skills_test"], ["skills_retest", "Retest allowed"]]},
    {"group": "Offer", "items": [["offer_start", "Offer sent"], ["reminders", "offer"], ["hired", "Hired"]]},
    {"group": "General", "items": [["under_review", "Results under recruiter review"], ["call_fallback", "Couldn't reach by call"],
                                   ["rejected", "Rejected (after recruiter decision)"]]},
]


# Follow-up cadences: texts and AI calls are configured separately, then combined into exact days.
PRESETS = {
    "persistent": {"texts": {"first": 1, "every_early": 1, "early_until": 7, "every_after": 3},
                   "calls": {"enabled": True, "first": 3, "every": 7}},
    "standard":   {"texts": {"first": 1, "every_early": 2, "early_until": 7, "every_after": 7},
                   "calls": {"enabled": True, "first": 5, "every": 14}},
    "light":      {"texts": {"first": 2, "every_early": 4, "early_until": 14, "every_after": 14},
                   "calls": {"enabled": False, "first": 10, "every": 30}},
}


def build_schedule(cadence: dict, give_up: int) -> list[tuple[int, str]]:
    """Turn a cadence into exact days. Same-day rule: if a text and a call land on the same day, the call
    goes out; if it isn't answered, the voicemail flow sends a text (so nobody gets both)."""
    t, c = cadence["texts"], cadence["calls"]
    texts, calls = set(), set()
    d = int(t["first"])
    while d < give_up:
        texts.add(d)
        d += int(t["every_early"]) if d < int(t["early_until"]) else int(t["every_after"])
    if c.get("enabled"):
        d = int(c["first"])
        while d < give_up:
            calls.add(d)
            d += int(c["every"])
    return [(day, "call" if day in calls else "sms") for day in sorted(texts | calls)]


def defaults() -> dict:
    return {
        "follow_up": {st: {**PRESETS["standard"], "preset": "standard"} for st in EDITABLE_STAGES},
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
    cadence = current()["follow_up"].get(stage)
    if not cadence:
        return list(config.DEFAULT_FOLLOW_UP)
    return build_schedule(cadence, give_up_after_days())


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
    give_up = int(proposed.get("give_up_after_days", current()["give_up_after_days"]))
    for stage, cad in (proposed.get("follow_up") or {}).items():
        name = stage.replace("_", " ")
        try:
            t, c = cad["texts"], cad["calls"]
            nums = [int(t["first"]), int(t["every_early"]), int(t["early_until"]), int(t["every_after"]), int(c["first"]), int(c["every"])]
        except (KeyError, TypeError, ValueError):
            errs.append(f"Follow-ups for {name}: fill in every number")
            continue
        if any(n < 1 for n in nums):
            errs.append(f"Follow-ups for {name}: all days must be 1 or more")
        if int(t["first"]) >= give_up:
            errs.append(f"Follow-ups for {name}: first text must be before day {give_up} (when reminders stop)")
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

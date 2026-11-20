"""Settings page API: read current values + defaults, save changes (validated), reset."""

import copy

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from .. import settings
from ..db import get_session

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings():
    return {"current": settings.current(), "defaults": settings.defaults(), "overrides": settings.overrides(),
            "template_labels": settings.EDITABLE_TEMPLATES, "editable_stages": settings.EDITABLE_STAGES,
            "sla_stages": settings.SLA_STAGES, "presets": settings.PRESETS,
            "template_groups": settings.TEMPLATE_GROUPS, "reminder_sets": __import__("app.config", fromlist=["REMINDER_SETS"]).REMINDER_SETS}


class Patch(BaseModel):
    changes: dict   # partial settings, same shape as "current"


def _deep_set(base: dict, changes: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in changes.items():
        out[k] = _deep_set(out.get(k, {}), v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


@router.put("")
def save(p: Patch, s: Session = Depends(get_session)):
    errors = settings.validate(p.changes)
    if errors:
        raise HTTPException(422, {"errors": errors})
    settings.save_overrides(s, _deep_set(settings.overrides(), p.changes))
    return {"ok": True, "current": settings.current()}


class Reset(BaseModel):
    path: list[str]   # e.g. ["templates", "intro"] or ["follow_up", "drug_test"]; [] resets everything


@router.post("/reset")
def reset(r: Reset, s: Session = Depends(get_session)):
    ov = copy.deepcopy(settings.overrides())
    if not r.path:
        ov = {}
    else:
        node = ov
        for k in r.path[:-1]:
            node = node.get(k, {})
        node.pop(r.path[-1], None)
    settings.save_overrides(s, ov)
    return {"ok": True, "current": settings.current()}

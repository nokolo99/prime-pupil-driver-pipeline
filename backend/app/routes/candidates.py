"""Recruiter-facing read endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import get_session
from ..models import (BackgroundCheck, Candidate, Clinic, Depot, DrugTest, Event, Message, Recruiter, ScreeningResult,
                      Stage, Step, Task, TaskStatus)

router = APIRouter(prefix="/api", tags=["recruiter"])


@router.get("/candidates")
def list_candidates(depot_id: int | None = None, recruiter_id: int | None = None, language: str | None = None,
                    channel: str | None = None, status: str | None = None, days: int | None = None,
                    stage: str | None = None, reason: str | None = None, applied_from: str | None = None,
                    applied_to: str | None = None, hired_from: str | None = None, hired_to: str | None = None,
                    session: Session = Depends(get_session)):
    """Pipeline list. Same filters as Insights so a chart bar can click through to the exact candidates."""
    from .insights import filtered
    cands = filtered(session, depot_id, recruiter_id, language, channel, status, days,
                     applied_from, applied_to, hired_from, hired_to)
    if stage:
        cands = [c for c in cands if c.stage.value == stage]
    if reason:
        cands = [c for c in cands if c.drop_reason and c.drop_reason.value == reason]
    return sorted(cands, key=lambda c: c.created_at, reverse=True)


@router.get("/candidates/{candidate_id}")
def get_candidate(candidate_id: int, session: Session = Depends(get_session)):
    c = session.get(Candidate, candidate_id)
    if not c:
        raise HTTPException(404, "Candidate not found")
    steps = session.exec(select(Step).where(Step.candidate_id == candidate_id)).all()
    screening_step = next((st for st in steps if st.stage == Stage.screening), None)
    return {
        "candidate": c,
        "steps": steps,
        "screening": session.get(ScreeningResult, screening_step.id) if screening_step else None,
        "background_check": next((session.get(BackgroundCheck, st.id) for st in steps if st.stage == Stage.background_check), None),
        "drug_test": _drug_detail(session, steps),
        "later": _later_details(session, steps),
        "messages": session.exec(select(Message).where(Message.candidate_id == candidate_id)
                                 .order_by(Message.created_at)).all(),
        "events": session.exec(select(Event).where(Event.candidate_id == candidate_id)
                               .order_by(Event.created_at)).all(),
        "tasks": session.exec(select(Task).where(Task.candidate_id == candidate_id)).all(),
    }


def _later_details(session: Session, steps):
    from ..models import Offer, PermitCheck, SkillsTest, Training
    out = {}
    for st in steps:
        for key, model in (("permit", PermitCheck), ("training", Training), ("skills_test", SkillsTest), ("offer", Offer)):
            row = session.get(model, st.id)
            if row:
                out[key] = row.model_dump()
    return out


def _drug_detail(session: Session, steps):
    st = next((st for st in steps if st.stage == Stage.drug_test), None)
    dt = session.get(DrugTest, st.id) if st else None
    if not dt:
        return None
    clinic = session.get(Clinic, dt.clinic_id) if dt.clinic_id else None
    return {**dt.model_dump(), "clinic_name": clinic.name if clinic else None}


@router.get("/flags")
def fyi_flags(session: Session = Depends(get_session)):
    """FYI items for recruiters (e.g. vendor results overdue). No action required."""
    rows = session.exec(select(Step).where(Step.flag_note != None, Step.completed_at == None)).all()  # noqa: E711
    return [{"candidate_id": st.candidate_id, "stage": st.stage, "note": st.flag_note} for st in rows]


@router.get("/tasks")
def open_tasks(session: Session = Depends(get_session)):
    return session.exec(select(Task).where(Task.status == TaskStatus.open)
                        .order_by(Task.priority, Task.created_at)).all()


@router.get("/events")
def recent_events(limit: int = 100, session: Session = Depends(get_session)):
    return session.exec(select(Event).order_by(Event.created_at.desc()).limit(limit)).all()


@router.get("/config")
def ui_config():
    from ..config import STAGE_SLA_DAYS
    from ..models import DropReason
    return {"stage_sla_days": STAGE_SLA_DAYS, "drop_reasons": [r.value for r in DropReason]}


@router.get("/lookups")
def lookups(session: Session = Depends(get_session)):
    return {
        "depots": session.exec(select(Depot)).all(),
        "recruiters": session.exec(select(Recruiter)).all(),
    }

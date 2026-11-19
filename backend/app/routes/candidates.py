"""Recruiter-facing read endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import get_session
from ..models import Candidate, Depot, Event, Message, Recruiter, ScreeningResult, Stage, Step, Task, TaskStatus

router = APIRouter(prefix="/api", tags=["recruiter"])


@router.get("/candidates")
def list_candidates(session: Session = Depends(get_session)):
    return session.exec(select(Candidate).order_by(Candidate.created_at.desc())).all()


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
        "messages": session.exec(select(Message).where(Message.candidate_id == candidate_id)
                                 .order_by(Message.created_at)).all(),
        "events": session.exec(select(Event).where(Event.candidate_id == candidate_id)
                               .order_by(Event.created_at)).all(),
        "tasks": session.exec(select(Task).where(Task.candidate_id == candidate_id)).all(),
    }


@router.get("/tasks")
def open_tasks(session: Session = Depends(get_session)):
    return session.exec(select(Task).where(Task.status == TaskStatus.open)
                        .order_by(Task.priority, Task.created_at)).all()


@router.get("/events")
def recent_events(limit: int = 100, session: Session = Depends(get_session)):
    return session.exec(select(Event).order_by(Event.created_at.desc()).limit(limit)).all()


@router.get("/lookups")
def lookups(session: Session = Depends(get_session)):
    return {
        "depots": session.exec(select(Depot)).all(),
        "recruiters": session.exec(select(Recruiter)).all(),
    }

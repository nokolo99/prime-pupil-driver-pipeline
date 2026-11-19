"""Recruiter actions on 'Needs you today' tasks. Every action is logged as a recruiter event
and decisions are written back to Workday (mock)."""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import workday
from ..conversation import advance, log_event, send, template
from ..db import get_session
from ..engine import reset_follow_up
from ..models import (Actor, Candidate, CandidateStatus, DropReason, Sender, Stage, Step, Task,
                      TaskStatus, now)

router = APIRouter(prefix="/api/tasks", tags=["recruiter actions"])

# Which actions make sense for which task type.
ALLOWED = {
    "review_knockout": {"approve", "reject"},
    "candidate_unresponsive": {"mark_dropped", "extend"},
}
DEFAULT_ACTIONS = {"dismiss"}


class ActionIn(BaseModel):
    action: Literal["approve", "reject", "mark_dropped", "extend", "dismiss"]
    reason: Optional[DropReason] = None
    note: Optional[str] = None
    recruiter_id: Optional[int] = None


def _current_step(s: Session, c: Candidate) -> Step:
    return s.exec(select(Step).where(Step.candidate_id == c.id, Step.stage == c.stage)
                  .order_by(Step.id.desc())).first()


@router.post("/{task_id}/action")
def act(task_id: int, a: ActionIn, s: Session = Depends(get_session)):
    task = s.get(Task, task_id)
    if not task or task.status != TaskStatus.open:
        raise HTTPException(404, "Open task not found")
    if a.action not in ALLOWED.get(task.type, set()) | DEFAULT_ACTIONS:
        raise HTTPException(400, f"'{a.action}' is not allowed for {task.type}")
    c = s.get(Candidate, task.candidate_id)
    rid = a.recruiter_id or c.recruiter_id

    if a.action == "approve":
        # Recruiter overrides the screening flag: continue to the next stage.
        log_event(s, c, "recruiter_approved", Actor.recruiter, actor_id=rid, note=a.note)
        advance(s, c, Stage.background_check)
        body, en = template("screening_passed", c.preferred_language)
        send(s, c, body, en, Sender.system)
        workday.push_disposition(s, c, "advance", "Screening flag reviewed and approved", by=str(rid))

    elif a.action == "reject":
        reason = a.reason or DropReason.failed_knockout
        c.status, c.drop_reason, c.drop_note = CandidateStatus.rejected, reason, a.note
        log_event(s, c, "recruiter_rejected", Actor.recruiter, actor_id=rid, reason=reason.value, note=a.note)
        body, en = template("rejected", c.preferred_language, first_name=c.first_name)
        send(s, c, body, en, Sender.system)
        workday.push_disposition(s, c, "reject", reason.value, by=str(rid))

    elif a.action == "mark_dropped":
        reason = a.reason or DropReason.no_response
        c.status, c.drop_reason, c.drop_note = CandidateStatus.dropped, reason, a.note
        log_event(s, c, "recruiter_marked_dropped", Actor.recruiter, actor_id=rid, reason=reason.value, note=a.note)
        workday.push_disposition(s, c, "dropped", reason.value, by=str(rid))

    elif a.action == "extend":
        # Restart the follow-up schedule from today.
        step = _current_step(s, c)
        reset_follow_up(step)
        step.started_at = now()
        log_event(s, c, "recruiter_extended_follow_up", Actor.recruiter, actor_id=rid)

    else:
        log_event(s, c, "task_dismissed", Actor.recruiter, actor_id=rid, task_type=task.type)

    task.status, task.resolution, task.resolved_by, task.resolved_at = TaskStatus.resolved, a.action, rid, now()
    s.commit()
    return {"ok": True}

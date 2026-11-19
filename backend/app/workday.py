"""Mock Workday connector (outbound).

The rest of the system calls these functions; it never knows whether Workday is real.
To go live, replace the body of _write() with Workday Recruiting API calls; nothing else changes.
"""

from sqlmodel import Session

from .models import Actor, Candidate, Event, WorkdayOutbox


def _write(s: Session, c: Candidate, action: str, payload: dict) -> None:
    s.add(WorkdayOutbox(candidate_id=c.id, workday_id=c.workday_id, action=action, payload=payload))
    s.add(Event(candidate_id=c.id, type="workday_synced", actor=Actor.system, details={"action": action, **payload}))


def push_disposition(s: Session, c: Candidate, decision: str, reason: str | None = None, by: str | None = None) -> None:
    """Recruiter decision (advance / reject / dropped) written back to the candidate's Workday record."""
    _write(s, c, "disposition", {"decision": decision, "reason": reason, "decided_by": by})

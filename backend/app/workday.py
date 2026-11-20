"""Workday connector.

Inbound (touchpoint 1): poll Workday's Get_Candidates for new applications (WORKDAY_INTAKE=poll), or
accept applicants posted directly (WORKDAY_INTAKE=direct, demo shortcut).
Outbound (touchpoints 2-6): decisions and stage changes written back to Workday.

The rest of the system calls these functions; it never knows whether Workday is real. WORKDAY_BASE_URL
points at the fake Workday built into this app; to go live, point it at the tenant and translate the
calls to Workday's SOAP envelopes here. Nothing else changes.
"""

import logging
import os

from sqlmodel import Session

from .models import Actor, Candidate, Event, WorkdayOutbox


log = logging.getLogger(__name__)


def intake_mode() -> str:
    return os.getenv("WORKDAY_INTAKE", "direct").lower()


def _base() -> str:
    return os.getenv("WORKDAY_BASE_URL", "http://localhost:8000/mock-workday").rstrip("/")


def get_candidates(updated_since: str | None) -> dict:
    """Workday Recruiting: Get_Candidates (changed since a timestamp)."""
    import httpx2 as httpx
    r = httpx.post(f"{_base()}/Recruiting/Get_Candidates", json={"updated_since": updated_since}, timeout=15)
    r.raise_for_status()
    return r.json()


def poll_new_applicants(s: Session) -> int:
    """Touchpoint 1 (production approach): ask Workday for applications since our last check and start
    a conversation for each one we haven't seen. Read-only; nothing to build on Prime Pupil's side."""
    from sqlmodel import select
    from .conversation import intake_applicant
    from .models import Candidate, Setting
    if intake_mode() != "poll":
        return 0
    mark = s.get(Setting, "workday_last_poll")
    try:
        data = get_candidates(mark.value if mark else None)
    except Exception as e:
        log.warning("Workday poll failed: %s", e)
        return 0
    added = 0
    for a in data["candidates"]:
        if s.exec(select(Candidate).where(Candidate.workday_id == a["job_application_id"])).first():
            continue
        depot_id = int(a["job_requisition_id"].split("-")[-1])
        intake_applicant(s, first_name=a["first_name"], last_name=a["last_name"], phone=a["phone"], email=a["email"],
                         depot_id=depot_id, language=a["preferred_language"], sms_consent=a["sms_consent"],
                         workday_id=a["job_application_id"], channel=a.get("contact_channel", "sms"))
        added += 1
    s.add(Setting(key="workday_last_poll", value=data["as_of"]) if not mark else mark)
    if mark:
        mark.value = data["as_of"]
    s.commit()
    if added:
        log.info("Workday poll: %d new applicant(s)", added)
    return added



def _write(s: Session, c: Candidate, action: str, payload: dict) -> None:
    s.add(WorkdayOutbox(candidate_id=c.id, workday_id=c.workday_id, action=action, payload=payload))
    s.add(Event(candidate_id=c.id, type="workday_synced", actor=Actor.system, details={"action": action, **payload}))


def push_disposition(s: Session, c: Candidate, decision: str, reason: str | None = None, by: str | None = None) -> None:
    """Recruiter decision (advance / reject / dropped) written back to the candidate's Workday record."""
    _write(s, c, "disposition", {"decision": decision, "reason": reason, "decided_by": by})


def push_stage(s: Session, c: Candidate, stage: str) -> None:
    """Keep the Workday candidate record's step in sync with ours."""
    _write(s, c, "stage_update", {"stage": stage})

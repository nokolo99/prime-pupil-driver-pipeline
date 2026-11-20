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

from .models import Actor, Candidate, Event, WorkdayOutbox, now


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
    """Queue a Workday write in the same transaction as the change (outbox). Delivered after commit."""
    s.add(WorkdayOutbox(candidate_id=c.id, workday_id=c.workday_id, action=action, payload=payload))
    s.add(Event(candidate_id=c.id, type="workday_synced", actor=Actor.system, details={"action": action, **payload}))
    s.info["workday_pending"] = True


def push_stage(s: Session, c: Candidate, stage: str) -> None:
    """Touchpoints 2-3: candidate moved forward -> Move_Candidate to the matching Workday step."""
    from .config import WORKDAY_STEPS
    _write(s, c, "Move_Candidate", {"stage": stage, "next_step": WORKDAY_STEPS.get(stage, stage)})


def push_disposition(s: Session, c: Candidate, decision: str, reason: str | None = None, by: str | None = None) -> None:
    """Touchpoint 4 (reject / drop) -> Move_Candidate to a disposition. Approvals are recorded as a note; the
    stage move that follows is what Workday sees. Touchpoint 6 (hired) -> Ready for Hire."""
    from .config import WORKDAY_DISPOSITIONS, WORKDAY_STEPS
    if decision in ("reject", "dropped"):
        _write(s, c, "Move_Candidate", {"decision": decision, "disposition": WORKDAY_DISPOSITIONS.get(reason or "other", "Other"),
                                        "reason": reason, "decided_by": by})
    elif decision == "hired":
        _write(s, c, "Move_Candidate", {"decision": "hired", "next_step": WORKDAY_STEPS["hired"], "reason": reason})
    else:  # recruiter approved a flag: note only
        s.add(Event(candidate_id=c.id, type="workday_note", actor=Actor.system, details={"decision": decision, "reason": reason}))


def initiate_offer(s: Session, c: Candidate, terms: dict) -> None:
    """Touchpoint 5: start the offer in Workday (Workday's offer process, templates and approvals)."""
    _write(s, c, "Offer", {"terms": terms})


def dispatch_outbox(limit: int = 50) -> int:
    """Deliver pending Workday writes (called right after commits and on every engine tick for retries)."""
    import httpx2 as httpx
    from sqlmodel import select
    from .db import engine
    sent = 0
    with Session(engine) as s:
        rows = s.exec(select(WorkdayOutbox).where(WorkdayOutbox.status.in_(["pending", "failed"]), WorkdayOutbox.attempts < 5)
                      .order_by(WorkdayOutbox.id).limit(limit)).all()
        for row in rows:
            row.attempts += 1
            if not row.workday_id or not row.workday_id.startswith("JA-"):
                row.status, row.response = "skipped", "No Workday job application (direct-mode or demo record)"
                continue
            body = {"job_application_id": row.workday_id, **{k: v for k, v in row.payload.items() if k in
                    ("next_step", "disposition", "terms")}}
            try:
                r = httpx.post(f"{_base()}/Recruiting/{row.action}", json=body, timeout=10)
                row.status = "sent" if r.status_code < 300 else "failed"
                row.response = r.text[:300]
                if row.status == "sent":
                    row.sent_at = now()
                    sent += 1
            except Exception as e:
                row.status, row.response = "failed", str(e)[:300]
        s.commit()
    return sent

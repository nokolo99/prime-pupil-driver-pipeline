"""Fake Workday Recruiting API (stand-in for Prime Pupil's tenant).

Real Workday Recruiting is SOAP web services (Get_Candidates, Move_Candidate, Offer, ...). This mock
keeps the same operation names and the fields we need, as JSON, so our connector (workday.py) is
written against Workday's shape. Swapping in the real tenant means pointing WORKDAY_BASE_URL at it
and translating to SOAP in the connector, not changing the rest of the system.
"""

import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import MockWorkdayApplication, now

router = APIRouter(prefix="/mock-workday", tags=["fake Workday"])


def requisition_for_depot(depot_id: int) -> str:
    return f"REQ-{depot_id:03d}"   # "School Bus Driver - <depot>"


class Apply(BaseModel):
    first_name: str
    last_name: str = ""
    phone: str
    email: Optional[str] = None
    depot_id: int
    preferred_language: str = "en"
    sms_consent: bool = True
    contact_channel: str = "sms"


@router.post("/career-site/apply")
def career_site_apply(a: Apply, s: Session = Depends(get_session)):
    """What happens when someone submits Prime Pupil's career-page form: a candidate + job application in Workday."""
    from ..phones import normalize_us
    row = MockWorkdayApplication(candidate_id=f"CAND-{secrets.randbelow(900000) + 100000}",
                                 job_application_id=f"JA-{secrets.token_hex(3).upper()}",
                                 job_requisition_id=requisition_for_depot(a.depot_id),
                                 **{**a.model_dump(exclude={"depot_id", "phone"}), "phone": normalize_us(a.phone)})
    s.add(row)
    s.commit()
    s.refresh(row)
    return {"candidate_id": row.candidate_id, "job_application_id": row.job_application_id}


class GetCandidatesReq(BaseModel):
    updated_since: Optional[datetime] = None


@router.post("/Recruiting/Get_Candidates")
def get_candidates(r: GetCandidatesReq, s: Session = Depends(get_session)):
    """Workday Get_Candidates: candidates/applications changed since a point in time."""
    q = select(MockWorkdayApplication).order_by(MockWorkdayApplication.updated_at)
    rows = s.exec(q).all()
    if r.updated_since:
        since = r.updated_since if r.updated_since.tzinfo else r.updated_since.replace(tzinfo=timezone.utc)
        rows = [x for x in rows if (x.updated_at if x.updated_at.tzinfo else x.updated_at.replace(tzinfo=timezone.utc)) > since]
    return {"candidates": [x.model_dump() for x in rows], "as_of": now().isoformat()}


@router.get("/applications")
def list_applications(s: Session = Depends(get_session)):
    """For the demo: see what's in fake Workday."""
    return s.exec(select(MockWorkdayApplication).order_by(MockWorkdayApplication.id.desc()).limit(50)).all()

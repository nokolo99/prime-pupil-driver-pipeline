"""Mock Workday integration: inbound "new applicant" event.

In production this would be a Workday Recruiting event/report integration. The payload
shape here is ours; the real connector would map Workday's fields onto it.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from ..conversation import intake_applicant
from ..db import get_session

router = APIRouter(prefix="/api/integrations/workday", tags=["workday (mock)"])


class NewApplicant(BaseModel):
    workday_id: Optional[str] = None
    first_name: str
    last_name: str = ""
    phone: str
    email: Optional[str] = None
    depot_id: int
    language: str = "en"
    sms_consent: bool = True


@router.post("/applicant")
def new_applicant(a: NewApplicant, session: Session = Depends(get_session)):
    c = intake_applicant(session, **a.model_dump())
    return {"candidate_id": c.id}

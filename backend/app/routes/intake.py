"""Mock Workday integration: inbound "new applicant" event.

In production this would be a Workday Recruiting event/report integration. The payload
shape here is ours; the real connector would map Workday's fields onto it.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ..conversation import intake_applicant
from ..db import get_session
from ..phones import normalize_us

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
    channel: str = "sms"  # sms or whatsapp (how the candidate prefers to be texted)
    first_contact: str = "text"  # text / call: how they want us to reach out first


@router.post("/applicant")
def new_applicant(a: NewApplicant, session: Session = Depends(get_session)):
    data = a.model_dump()
    try:
        data["phone"] = normalize_us(a.phone)
    except ValueError as e:
        raise HTTPException(422, str(e))
    c = intake_applicant(session, **data)
    return {"candidate_id": c.id, "phone": c.phone}

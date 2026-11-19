"""Browser chat simulator. Increment 0: echo only. Increment 1 plugs in the screening agent."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from ..db import get_session

router = APIRouter(prefix="/api", tags=["simulator"])


class ChatIn(BaseModel):
    phone: str
    body: str


@router.post("/chat")
def chat(msg: ChatIn, session: Session = Depends(get_session)):
    return {"reply": f"(echo) {msg.body}"}

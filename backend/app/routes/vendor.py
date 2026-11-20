"""Mock vendor surfaces + vendor integrations.

- /vendor/bg/{order}  and /vendor/drug/{case}: stand-ins for the vendors' candidate-facing pages
  (the links we text). Submitting them fires the same events a real vendor would.
- /api/integrations/bg-vendor/email: inbound result email (prod: an inbound-email webhook).
- /api/integrations/drug-vendor/webhook: drug test vendor events (John: the vendor offers an integration).
"""

import html
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import ai, stages
from ..config import LOCAL_TZ
from ..conversation import create_task, log_event
from ..db import get_session
from ..models import Actor, BackgroundCheck, Candidate, Clinic, DrugTest, Step, now

router = APIRouter(tags=["vendors (mock)"])

PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
body{{font-family:system-ui,-apple-system,sans-serif;max-width:480px;margin:0 auto;padding:16px;background:#f5f5f4;color:#1c1917}}
.card{{background:#fff;border-radius:12px;padding:16px;margin:12px 0;box-shadow:0 1px 2px #0001}}
.brand{{font-weight:700;color:{color}}} label{{display:block;margin:10px 0 4px;font-size:14px;color:#57534e}}
input,select{{width:100%;padding:8px;border:1px solid #d6d3d1;border-radius:8px;font-size:16px;box-sizing:border-box}}
button{{width:100%;padding:12px;margin-top:16px;background:{color};color:#fff;border:0;border-radius:8px;font-size:16px}}
.note{{font-size:12px;color:#78716c}} .opt{{display:flex;gap:8px;align-items:flex-start;margin:8px 0}} .opt input{{width:auto}}
</style></head><body><div class="brand">{brand}</div>{body}
<p class="note">Demo vendor page for the Prime Pupil prototype. Do not enter real personal information.</p></body></html>"""


def _page(title: str, brand: str, color: str, body: str) -> HTMLResponse:
    return HTMLResponse(PAGE.format(title=title, brand=brand, color=color, body=body))


# ---------- Background check vendor (candidate form) ----------

@router.get("/vendor/bg/{order_id}", response_class=HTMLResponse)
def bg_form(order_id: str, s: Session = Depends(get_session)):
    bc = s.exec(select(BackgroundCheck).where(BackgroundCheck.vendor_order_id == order_id)).first()
    if not bc:
        raise HTTPException(404, "Order not found")
    c = s.get(Candidate, s.get(Step, bc.step_id).candidate_id)
    if bc.form_completed_at:
        return _page("Submitted", "Checkpoint Screening", "#1d4ed8", '<div class="card"><h2>All set ✓</h2><p>Your form was submitted. Results usually take 3–5 days.</p></div>')
    name = html.escape(f"{c.first_name} {c.last_name}")
    return _page("Background check", "Checkpoint Screening", "#1d4ed8", f"""
<div class="card"><h2>Background check for Prime Pupil</h2><p>Order {order_id} · About 10 minutes</p>
<form method="post"><label>Full legal name</label><input value="{name}" readonly>
<label>Date of birth</label><input value="01/01/1980 (demo)" readonly>
<label>Driver's license # and state</label><input value="D123-4567-8901 NY (demo)" readonly>
<label>Addresses, last 7 years</label><input value="(demo data)" readonly>
<div class="opt"><input type="checkbox" required id="a"><label for="a">I authorize a background check and motor vehicle record check (FCRA disclosure).</label></div>
<button type="submit">Submit</button></form></div>""")


@router.post("/vendor/bg/{order_id}", response_class=HTMLResponse)
def bg_form_submit(order_id: str, s: Session = Depends(get_session)):
    stages.bg_form_completed(s, order_id)  # what the vendor's "form completed" event would trigger
    return bg_form(order_id, s)


class BgWebhookIn(BaseModel):
    order_id: str
    event: Literal["form_completed", "result"]
    status: Optional[Literal["clear", "consider"]] = None
    summary: str = ""


@router.post("/api/integrations/bg-vendor/webhook")
def bg_webhook(e: BgWebhookIn, s: Session = Depends(get_session)):
    """Background-check vendor integration (John: orders and results go through it). Email parsing is the fallback."""
    if e.event == "form_completed":
        c = stages.bg_form_completed(s, e.order_id)
    else:
        c = stages.bg_result(s, e.order_id, e.status or "consider",
                             e.summary or ("No records found." if e.status == "clear" else "Report needs review."))
    if c is None:
        raise HTTPException(404, "Unknown order (or already processed)")
    return {"ok": True}


class BgEmailIn(BaseModel):
    sender: str = ""
    subject: str
    body: str


@router.post("/api/integrations/bg-vendor/email")
def bg_email(e: BgEmailIn, s: Session = Depends(get_session)):
    """Inbound vendor result email. Claude reads it; code decides what happens."""
    parsed = ai.parse_bg_email(e.subject, e.body)
    bc = s.exec(select(BackgroundCheck).where(BackgroundCheck.vendor_order_id == parsed.order_id)).first() if parsed.order_id else None
    if not bc:
        # Not a result for any order we placed (or no order number): ignore, keep a log line.
        import logging
        logging.getLogger(__name__).warning("Unmatched vendor email: %r", e.subject[:80])
        return {"processed": False, "parsed": parsed.model_dump()}
    if parsed.status == "unknown":
        # Matched an order but the result is unclear: never guess. A recruiter reads it.
        c = s.get(Candidate, s.get(Step, bc.step_id).candidate_id)
        create_task(s, c, "unreadable_vendor_email", f"Couldn't read background result email: “{e.subject[:80]}”", priority=2)
        s.commit()
        return {"processed": False, "parsed": parsed.model_dump()}
    stages.bg_result(s, parsed.order_id, parsed.status, parsed.summary)
    return {"processed": True, "parsed": parsed.model_dump()}


# ---------- Drug test vendor (authorization + booking) ----------

def _slots() -> list[datetime]:
    local_now = now().astimezone(ZoneInfo(LOCAL_TZ))
    out = []
    for d in range(1, 6):
        day = (local_now + timedelta(days=d)).replace(minute=0, second=0, microsecond=0)
        for h in (9, 11, 14, 16):
            out.append(day.replace(hour=h))
    return out


@router.get("/vendor/drug/{case_id}", response_class=HTMLResponse)
def drug_page(case_id: str, s: Session = Depends(get_session)):
    dt = s.exec(select(DrugTest).where(DrugTest.vendor_case_id == case_id)).first()
    if not dt:
        raise HTTPException(404, "Case not found")
    c = s.get(Candidate, s.get(Step, dt.step_id).candidate_id)
    clinics = stages.nearby_clinics(s, c)
    booked = ""
    if dt.appointment_at:
        booked = f'<div class="card">Current booking: <b>{html.escape(s.get(Clinic, dt.clinic_id).name)}</b>, {stages.fmt_when(dt.appointment_at)}. Pick again below to reschedule.</div>'
    clinic_opts = "".join(f'<div class="opt"><input type="radio" name="clinic_id" value="{cl.id}" required id="c{cl.id}"><label for="c{cl.id}"><b>{html.escape(cl.name)}</b><br>{html.escape(cl.address)} · {html.escape(cl.hours)}</label></div>' for cl in clinics)
    slot_opts = "".join(f'<option value="{t.astimezone(timezone.utc).isoformat()}">{stages.fmt_when(t)}</option>' for t in _slots())
    return _page("DOT drug test", "ClinicLink", "#0f766e", f"""{booked}
<div class="card"><h2>DOT drug test for Prime Pupil</h2><p>Case {case_id} · About 15 minutes at the clinic. Bring a photo ID.</p>
<form method="post"><div class="opt"><input type="checkbox" required id="auth"><label for="auth">I authorize a DOT-regulated drug test and release of results to Prime Pupil.</label></div>
<label>Choose a clinic</label>{clinic_opts}<label>Choose a time</label><select name="when">{slot_opts}</select>
<button type="submit">Sign &amp; book</button></form></div>""")


@router.post("/vendor/drug/{case_id}", response_class=HTMLResponse)
def drug_book(case_id: str, clinic_id: int = Form(...), when: str = Form(...), s: Session = Depends(get_session)):
    stages.drug_event(s, case_id, "appointment_booked", clinic_id=clinic_id, appointment_at=datetime.fromisoformat(when))
    dt = s.exec(select(DrugTest).where(DrugTest.vendor_case_id == case_id)).first()
    return _page("Booked", "ClinicLink", "#0f766e",
                 f'<div class="card"><h2>You\'re booked ✓</h2><p>{html.escape(s.get(Clinic, dt.clinic_id).name)}<br>{stages.fmt_when(dt.appointment_at)}</p><p>Bring a photo ID. You\'ll get a reminder the day before.</p></div>')


class DrugEventIn(BaseModel):
    case_id: str
    event: Literal["appointment_booked", "collected", "no_show", "result"]
    result: Optional[Literal["negative", "non_negative"]] = None
    clinic_id: Optional[int] = None
    appointment_at: Optional[datetime] = None


@router.post("/api/integrations/drug-vendor/webhook")
def drug_webhook(e: DrugEventIn, s: Session = Depends(get_session)):
    c = stages.drug_event(s, e.case_id, e.event, clinic_id=e.clinic_id, appointment_at=e.appointment_at, result=e.result)
    if not c:
        raise HTTPException(404, "Unknown case")
    return {"ok": True}


# ---------- Training (Zoom stand-in), skills test platform, offer e-signature ----------

from ..models import Offer, SkillsTest, Training  # noqa: E402


@router.get("/vendor/training/{code}", response_class=HTMLResponse)
def training_page(code: str, s: Session = Depends(get_session)):
    tr = s.exec(select(Training).where(Training.session_link.endswith(code))).first()
    if not tr:
        raise HTTPException(404, "Session not found")
    return _page("CDL training", "Zoom (demo)", "#2563eb",
                 f'<div class="card"><h2>Prime Pupil paid CDL training</h2><p>Cohort starts {stages.fmt_when(tr.cohort_start)}.</p>'
                 '<p>In production this link opens the Zoom meeting.</p></div>')


@router.get("/vendor/skills/{test_id}", response_class=HTMLResponse)
def skills_page(test_id: str, s: Session = Depends(get_session)):
    st = s.exec(select(SkillsTest).where(SkillsTest.test_id == test_id)).first()
    if not st:
        raise HTTPException(404, "Test not found")
    return _page("Skills test", "DriveAssess (demo)", "#7c3aed",
                 f'<div class="card"><h2>CDL skills assessment</h2><p>Test {test_id} · attempt {st.attempts}</p>'
                 '<p>In production the candidate takes the assessment here; the platform sends the result to Prime Pupil automatically.</p></div>')


class SkillsResultIn(BaseModel):
    test_id: str
    result: Literal["pass", "fail"]
    score: Optional[int] = None


@router.post("/api/integrations/skills-platform/webhook")
def skills_webhook(e: SkillsResultIn, s: Session = Depends(get_session)):
    c = stages.skills_result(s, e.test_id, e.result, e.score)
    if not c:
        raise HTTPException(404, "Unknown test")
    return {"ok": True}


@router.get("/vendor/offer/{offer_id}", response_class=HTMLResponse)
def offer_page(offer_id: str, s: Session = Depends(get_session)):
    o = s.exec(select(Offer).where(Offer.offer_id == offer_id)).first()
    if not o:
        raise HTTPException(404, "Offer not found")
    c = s.get(Candidate, s.get(Step, o.step_id).candidate_id)
    if o.signed_at:
        return _page("Signed", "SignDesk (demo)", "#15803d", '<div class="card"><h2>Signed ✓</h2><p>Welcome to Prime Pupil! Your recruiter will be in touch with your start details.</p></div>')
    if o.declined_at:
        return _page("Declined", "SignDesk (demo)", "#15803d", '<div class="card"><h2>Offer declined</h2><p>Your recruiter will follow up.</p></div>')
    rows = "".join(f"<tr><td style='color:#78716c;padding:4px 8px 4px 0'>{html.escape(k.replace('_', ' ').title())}</td><td>{html.escape(str(v))}</td></tr>" for k, v in o.terms.items())
    return _page("Your offer", "SignDesk (demo)", "#15803d", f"""
<div class="card"><h2>Offer of employment</h2><p>Dear {html.escape(c.first_name)}, Prime Pupil Transportation is pleased to offer you the following position:</p>
<table>{rows}</table><p class="note">Placeholder terms for the prototype.</p>
<form method="post"><input type="hidden" name="decision" value="sign"><label>Type your full name to sign</label><input name="signature" required value="{html.escape(c.first_name + ' ' + c.last_name)}">
<button type="submit">Sign offer</button></form>
<form method="post"><input type="hidden" name="decision" value="decline"><button type="submit" style="background:#a8a29e">Decline</button></form></div>""")


@router.post("/vendor/offer/{offer_id}", response_class=HTMLResponse)
def offer_submit(offer_id: str, decision: str = Form(...), s: Session = Depends(get_session)):
    stages.offer_response(s, offer_id, signed=(decision == "sign"))
    return offer_page(offer_id, s)

# Scope Decisions (option map — final cut lives in DESIGN.md §6)

Goal: cut total time-to-hire (~90 days) → fewer candidates lost → more hires.

## Stage 1: Screening
- ✅ NEW: Mock career-page application form → instant first text (John: apps come via career page; first response takes 1–2 wks)
- ✅ Texting agent (SMS, multilingual)
- ✅ Voice agent
- ⬜ Mobile web form
- ✅ Auto-knockout rules
- ✅ Instant handoff to next stage
- ✅ Re-engagement of stalled screeners
- ⬜ Self-serve recruiter callback booking

## Stage 2: Background check & driving record
- ✅ Consent/authorization in the conversation
- ✅ Document collection (license photo etc.)
- ✅ Vendor status tracking
- ✅ Auto vendor kickoff — mock vendor API (assumes vendor has an API; confirm in email 2)
- ✅ Keep candidate warm
- ❌ Parallelize with drug test — John: strictly in order
- ✅ Exceptions → recruiter review (John: recruiter reviews all rejections)
- ⬜ Adverse action tracking — mention in Q&A only

## Stage 3: DOT drug test
- ✅ Clinic scheduling
- ✅ Clinic finder
- ✅ Reminders
- ✅ No-show detection & rebooking
- ✅ Clinic email result parsing
- ✅ Overdue-result alert
- ✅ Non-negative → recruiter review (required)

## Stage 4: CDL (permit, training, skills test)
- ✅ Permit test prep (daily SMS quiz, multilingual)
- ✅ DMV help — send link/instructions + nudges (candidate books own; one state)
- ✅ Training enrollment — send Zoom link + start date (mock)
- ⬜ Training progress tracking — dropped (training moves fast)
- ✅ In-training check-ins (flight risk)
- ✅ Skills test — send link; results via mock platform webhook
- ✅ Pay & logistics FAQ

## Stage 5: Offer
- ✅ Auto-generated offer — no approval needed (John)
- ✅ E-signature via text link
- ✅ Onboarding paperwork (I-9, W-4, direct deposit)
- ⬜ Route assignment
- ✅ Offer Q&A (multilingual)
- ⬜ First-day prep
- ⬜ Workday write-back (covered under cross-cutting)

## Recruiter dashboard
- ✅ Pipeline board (by stage, location, recruiter)
- ✅ "Needs you today" queue
- ✅ "Handled for you" log
- ✅ Candidate timeline
- ✅ Drop-off reasons
- ✅ Recruiter takeover of conversations
- ❓ Real-time updates — maybe; brief explicitly asks for "things updating as we watch"
- ✅ VP metrics view
- ✅ SLA breach alerts

## Shared systems
- ✅ Stage rules & timers (deterministic; AI never decides advancement)
- ✅ Escalation rules
- ✅ AI guardrails
- ✅ Workday connection — mocked adapter (swap for real API later) — ❓ Q12
- ⬜ Multi-location config
- ✅ TCPA consent & opt-out (Twilio handles STOP natively)
- ✅ Audit trail
- ✅ "Fast-forward time" demo control

---
## Final cut & build sequence
See DESIGN.md §6–7 (source of truth).

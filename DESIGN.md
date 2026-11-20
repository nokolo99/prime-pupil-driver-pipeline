# Prime Pupil Driver Pipeline: Design Doc

**Author:** Nneka · **Status:** Draft, in progress · **Last updated:** 2026-11-19

---

## 1. The problem

Prime Pupil runs school buses for districts. Every route needs a qualified driver, and they can't hire fast enough. When a route has no driver, kids are late and district contracts are at risk.

It takes **~90 days** to turn an interested candidate into a driver on a route, and most candidates are lost along the way. Not because they're poor fits, but because of **gaps between steps**: a recruiter forgets to follow up, a clinic appointment slips, a test result sits in an inbox for a week.

Today the process runs on Workday, recruiter spreadsheets, and texts from work phones. Clinic results arrive by email. **6 recruiters** each juggle **100+ candidates**, and no one can easily see where each candidate is.

**The hiring process:**
1. Screening
2. Background check & driving record
3. DOT drug test at a clinic
4. CDL: permit, paid training, skills test
5. Offer

## 2. Goal

**Cut total time to hire → lose fewer candidates → roughly double hires.**

These are one causal chain: long waits between steps cause drop-off, so shrinking the gaps serves both goals.

Success metrics (to confirm with Prime Pupil):
- Days from first contact to offer
- Conversion rate per stage (where people drop)
- Time candidates spend waiting per stage
- Hires per month

## 3. Who we're serving

| Stakeholder | What they care about |
|---|---|
| **VP of Operations** (decision maker) | Runs at the speed and volume needed, across all locations; handles edge cases |
| **Director of Recruiting** | Experience for recruiters and candidates |
| **IT** | Integration with Workday and existing systems |
| **Candidates** | Hourly workers, career changers, retirees applying from a phone between shifts. ~1/3 prefer Spanish. Older phones, limited data; no app, no password. Some prefer a call to reading. |
| **Recruiters** | One place to see where everyone is, why they stopped, and who needs them today |

## 4. Discovery

Questions sent to Prime Pupil on 2026-11-19 (see `email1_sent.md`). Full question bank in `question_bank.md`.

Answers received 2026-11-19 (full text in `john_reply_1.md`).

| # | Question | Answer | Design impact |
|---|---|---|---|
| 1 | Biggest time sink; fix first | Recruiters spend most time **chasing candidates** and checking inboxes. Fix first: **follow-ups + knowing where every candidate is.** | Confirms core: automated follow-ups + pipeline visibility are the priority. |
| 2 | Candidate journey | Apply via **career page form** → recruiter reaches out in days to a week → everything via texts/calls from recruiter work phones. Nothing automated. | Entry point is a **web application form**, not a text. First contact should be instant and automatic. |
| 3 | How steps work | **BG check:** recruiter orders on vendor website; results by email in 3–5 days. **Drug test:** recruiter emails auth form; candidate visits vendor clinic; results 2–5 days; **vendor offers integration.** **Permit:** candidate books own DMV; verified at the end. **Training:** paid, Zoom. **Skills test:** online platform, **offers integration.** | BG results → email parsing. Drug test + skills test → mock vendor webhooks. Permit → candidate-driven; nudges + verify before offer. |
| 4 | Volume | ~**300 applicants/mo, 12 depots, 1 state.** Hire ~**17/mo, need ~35.** Peak July–Aug. | 17/300 ≈ 6% conversion; 35 needs ≈ 12%. Depot is a core field. One state = one set of DMV rules. Must handle peak volume. |
| 5 | Time per stage | Screening **1–2 wks** (slow first response; candidates take other jobs). BG **3–4 wks** (candidates don't fill out vendor form; no follow-up). Drug test **3–4 wks, biggest drop-off** (procrastinate / miss appointments; reminder after reminder). Training ~1 wk, skills test a few days. Permit wait **1–2 wks** at the end. | **~70% of the 90 days is waiting on candidates to act** in BG + drug test. The product's job: get candidates to take action, and surface who's stuck. |
| 6 | Parallel steps? | **Strictly in order:** screening → BG → drug test → permit → training → skills test → offer. Don't want to pay for later steps early. | No parallelization. Stage engine is a strict sequence. |
| 7 | Human involvement | **Recruiter reviews before any rejection** (incl. failed drug tests and screening). **Offers can go out automatically.** | System never rejects: failures create a recruiter review task. Offer is auto-sent once all steps clear. |

**Key takeaway:** the 90 days is mostly candidates not doing their part (filling out the BG form, going to the clinic) and nobody following up. The highest-leverage product is an **always-on follow-up system** that gets candidates to act, plus a **clear view of who's stuck**.

### Email 2 answers (2026-11-19, full text in `john_reply_2.md`)

| Topic | Answer | Design impact |
|---|---|---|
| Screening | Four automatic fails: under 21, licensed < 3 years, DUI in past 7 years, unwilling to take a drug test | Replace our assumed questions with these four |
| Background check | Vendor offers an integration: order + results without the website | Confirms automatic ordering; results can come via integration (email parsing becomes fallback) |
| Drug test authorization | Vendor's standard authorization, generated per candidate; can be created via the integration | Confirms automatic authorization |
| CDL permit | Candidate books/takes DMV test alone; doesn't share permit during the process; recruiter asks for it and verifies at the very end, before the offer | Our flow collects the photo at the permit stage (earlier) — a deliberate change to decide on |
| Training | Trainer checks Zoom attendance and marks completion in a shared spreadsheet; recruiters check it "when they remember" | Another inbox-style gap: completion sits in a spreadsheet; automate the handoff |
| Texting | Consider WhatsApp, the trial account, or other providers; they'll send phone numbers in advance; $100 reimbursable | Opens real-phone options for the demo |

## 5. Options considered

We mapped what we *could* build for each of the 5 stages plus the recruiter side and shared systems. Full list with picks in `scope_decisions.md`.

## 6. Scope: what we're building and why

**Principle:** John told us most of the 90 days is lost in **screening (slow first contact)**, the **background check**, and the **drug test**, waiting on candidates to act. So we go **deep on stages 1–3** and **light on 4–5**.

### Tier 1: Must build (core story)
| Area | What | Why |
|---|---|---|
| Entry | Mock career-page application → first text within seconds | Fixes 1–2 week first response |
| Screening | SMS agent (EN/ES), knockout questions → recruiter review, re-engage stalled candidates | John's #1: follow-ups |
| Stage engine | Strict sequence, timers, nudges, escalation, fast-forward, opt-out, audit trail | This *is* "follow-ups"; everything depends on it |
| Background check | Auto-order via mock vendor API, text form link + nudges, results via email → parsed, flags → recruiter review | 3–4 weeks lost here |
| Drug test | Authorization + clinic finder, reminders, no-show → rebook, results via mock vendor webhook, overdue alert, non-negative → recruiter review | Biggest drop-off |
| Recruiter dashboard | Pipeline by depot, Needs you today, Handled for you, timeline, drop-off reasons, stuck alerts | John's #1: knowing where every candidate is |
| Voice | Phone screening, EN/ES | Candidates who prefer calls; brief calls it out |

### Tier 2: Build if time allows (in order)
1. Mock Workday connector (IT's moment)
2. Stages 4–5, thin: DMV link + nudges, Zoom link, skills test via mock webhook, auto offer + e-sign link
3. Real-time updates (polling) + recruiter takeover of a conversation
4. Simple VP metrics: funnel + days per stage

### Tier 3: Not building (and why)
| Item | Why not |
|---|---|
| Permit quiz, in-training check-ins | Training "moves quickly"; not where people are lost |
| Onboarding paperwork (I-9, W-4) | After the offer; outside the 90-day problem |
| License photo, separate consent step | BG vendor's own form handles consent and documents |
| Dedicated pay/offer FAQ | The AI agent answers general questions anyway |
| Multi-location config | Depot field covers it; per-depot rules later |
| Adverse action tracking | Recruiters own rejections; discuss in Q&A |

## 7. Build sequence

| # | Increment | Tier | Done when |
|---|---|---|---|
| 0 | Skeleton | 1 | Backend, DB, frontend talking; browser chat simulator |
| 1 | Entry + screening | 1 | Career-page form triggers first message; EN/ES screening; knockouts → review task; candidate on dashboard with timeline |
| 2 | Stage engine + recruiter loop | 1 | Timers, nudges, re-engagement, fast-forward; Needs-you / Handled-for-you; stuck alerts; drop-off reasons |
| 3 | Real SMS ✅ | 1 | Same flow over Twilio on a real phone; opt-out |
| 4 | Background check + drug test ✅ | 1 | Mock BG vendor (auto-order, email results parsed); clinic finder, reminders, no-show, mock drug-test webhook; overdue alerts; failures → review |
| 5 | Voice | 1 | Phone screening, EN/ES |
| 6 | Workday mock connector | 2 | Stage changes sync to mock Workday |
| 7 | Stages 4–5 ✅ | 2 | Permit nudges, Zoom link, skills-test webhook, auto offer + e-sign |
| 8 | Real-time ✅ + VP Insights ✅ (takeover out of scope) | 2 | Dashboard auto-refreshes; recruiter can reply; funnel view |
| 9 | Deploy + demo data | — | Hosted, seeded with realistic candidates |
| 10 | UI polish ✅ | — | Visual cleanup across all screens (deliberately last) |

## 8. Architecture

```
 Candidate's phone ──SMS / voice──> Twilio ──webhook──┐
                                                      ▼
 Browser chat simulator ──────────────>  PYTHON BACKEND (FastAPI)
 (TypeScript, for dev + backup)            • conversation agent (Claude API)
                                           • stage rules, timers, reminders
 Recruiter dashboard  <────JSON──────      • clinic email parsing
 (TypeScript / React)                      • mock Workday + vendor connectors
                                           • SQLite
```

- **Backend:** Python + FastAPI + SQLModel (on SQLAlchemy) + SQLite. Owns all logic.
- **Database:** SQLite for the prototype (single file, zero setup). **Postgres in production** (concurrent writes from recruiters, webhooks and timers; managed backups). With SQLModel, the switch is mostly the connection string.
- **Frontend:** TypeScript + React. Recruiter dashboard and chat simulator.
- **Why split:** each side in the language the author is strongest in; maps to the brief's two sides (candidate experience in backend over SMS/voice, recruiter experience in dashboard).
- **Hosting:** build locally (ngrok for real SMS testing); deploy to Render/Railway at the end if time permits. FastAPI serves the built frontend, so it's a single deploy.

## 9. Core design principle: rules decide, AI talks

- A **deterministic stage engine** owns the process: which stage a candidate is in, time limits per stage, what happens next, and when to escalate to a human.
- **AI handles conversation and extraction only:** talking to candidates in their language, answering questions, reading clinic emails and documents.
- **AI never makes hiring decisions.** Every message and action is logged with who/what did it (system vs. recruiter).

_Why:_ predictable behavior on edge cases (VP), clear boundaries and auditability (IT), and the AI's mistakes stay low-stakes.

## 10. Data model

### Overview

```
Depot ─┬─< Candidate >── Recruiter
       │      │
       │      ├──< Step ──── ScreeningResult   (1:1, detail)
       │      │        ├──── BackgroundCheck   (1:1, detail)
       │      │        └──── DrugTest >── Clinic
       │      ├──< Message
       │      ├──< Event
       │      └──< Task
       └──< Clinic
```

- **Step** is a general table the stage engine works on (timers, nudges, stuck alerts are the same for every stage).
- **Detail tables** hold step-specific fields, linked 1:1 to a Step. Only steps with specific data get one (class table inheritance). Thin steps (permit, training) live in Step alone until they need more.

### Stages (strict order, per John)
`application → screening → background_check → drug_test → cdl_permit → training → skills_test → offer → hired`

### Statuses
**Candidate.status** (what's happening now):
`in_progress` (system is acting) · `waiting_on_candidate` · `waiting_on_vendor` · `needs_review` (a recruiter must act) · `dropped` · `rejected` · `hired`

**Step.status:** `not_started` · `in_progress` · `waiting_on_candidate` · `waiting_on_vendor` · `passed` · `failed`

### Drop-off reasons (fixed list + optional note)
`no_response` · `failed_knockout` · `failed_background_check` · `failed_drug_test` · `withdrew` · `took_another_job` · `other`

### Tables

**Candidate**
| Field | Notes |
|---|---|
| id | |
| first_name, last_name, phone, email | |
| preferred_language | `en`, `es`, other |
| preferred_channel | `sms` or `voice` |
| depot_id, recruiter_id | |
| source | e.g. `career_page` |
| stage, status | see above; status is a convenience copy kept in sync by the engine for fast dashboard queries |
| stage_entered_at | powers "days in stage" and stuck alerts |
| last_contacted_at, last_reply_at | |
| drop_reason, drop_note | set when dropped/rejected |
| sms_consent_at, opted_out | compliance |
| workday_id | nullable; set when synced to Workday |
| created_at | |

**Step** (general)
| Field | Notes |
|---|---|
| id, candidate_id, stage | |
| status | see above |
| due_at | when the engine considers this step stuck |
| nudge_count, last_nudged_at | how many reminders sent at this step |
| started_at, completed_at | |
| result | `pass`, `fail`, `flag` (flag → recruiter review) |

**ScreeningResult** (detail of Step)
| Field | Notes |
|---|---|
| step_id | |
| is_21_plus, has_valid_license, years_licensed | knockout inputs |
| recent_violations, violations_note | |
| availability_ok | split shifts, school-year schedule |
| has_cdl_or_permit | info only (screening Q5) |
| knockout_flags | list of failed criteria; any flag → review task, never auto-reject |

**BackgroundCheck** (detail of Step)
| Field | Notes |
|---|---|
| step_id | |
| vendor_order_id | from mock vendor API |
| form_link, form_completed_at | the candidate-side form that's the real bottleneck |
| report_status | `ordered` · `form_pending` · `in_progress` · `clear` · `consider` |
| report_received_at, flags | parsed from the vendor's result email |

**DrugTest** (detail of Step)
| Field | Notes |
|---|---|
| step_id | |
| auth_sent_at | authorization form sent |
| clinic_id, appointment_at | |
| no_show_count | |
| vendor_case_id | |
| result, result_received_at | `negative` · `non_negative` · `cancelled`; non-negative → review task |

**Message**
| Field | Notes |
|---|---|
| id, candidate_id | |
| direction | `in` / `out` |
| channel | `sms` · `voice` · `web` (simulator) |
| sender | `candidate` · `ai` · `system` · `recruiter` |
| body, language | |
| translation_en | English translation shown to recruiters under non-English messages |
| provider_id | Twilio message/call ID |
| created_at | |

**Event** (timeline + audit trail + "Handled for you")
| Field | Notes |
|---|---|
| id, candidate_id | |
| type | e.g. `applied`, `stage_changed`, `nudge_sent`, `result_received`, `task_created`, `opted_out` |
| actor | `system` · `ai` · `recruiter` · `candidate` · `vendor` |
| actor_id | which recruiter, if any |
| details | JSON |
| created_at | |

**Task** ("Needs you today")
| Field | Notes |
|---|---|
| id, candidate_id | |
| type | e.g. `review_knockout`, `review_background_flag`, `review_drug_result`, `candidate_unresponsive`, `candidate_question` |
| reason | human-readable explanation shown to the recruiter |
| priority | |
| status | `open` / `resolved` |
| assigned_recruiter_id | |
| resolution, resolved_by, resolved_at | e.g. approved / rejected / contacted |
| created_at | |

**Lookups:** Depot (id, name, city) · Recruiter (id, name, depot) · Clinic (id, name, address, hours, depot)

### How the model answers the recruiter's questions
| Question | Answered by |
|---|---|
| Where is everyone? | Candidate.stage + status, filter by depot |
| Why did they stop? | Event history + drop_reason |
| What needs me today? | open Tasks |
| What did the system handle? | Events where actor = system / ai |
| Audit trail | Events |

## 11. Candidate experience (UX)

### Journey (persona: Maria, prefers Spanish)
| Stage | What she experiences |
|---|---|
| Applies | Short career-page form on her phone: name, phone, depot, language, SMS consent checkbox |
| Within seconds | First text in her language: intro + "Do you have 5 minutes for a few quick questions?" |
| Screening | ~5 questions, one at a time, answered in her own words. Pass → straight to next step. Knockout flag → "A recruiter will follow up within 1 business day" (never rejected by text) |
| Background check | Vendor form link immediately ("takes ~10 minutes"); reminders if not completed; notified when results arrive |
| Drug test | Authorization + nearest 2–3 clinics (hours, map link); reminders day before + morning of; no-show → "Want to go tomorrow instead?" |
| Throughout | Can ask anything; "talk to a person" → recruiter task; STOP anytime |

### Screening questions (from John, email 2)
| # | Question | Automatic fail (→ recruiter review, never rejected by text) |
|---|---|---|
| 1 | Are you 21 or older? | Under 21 |
| 2 | How many years have you had your driver's license? | Under 3 years |
| 3 | Have you had a DUI in the past 7 years? | Yes |
| 4 | Are you willing to take a DOT drug test? | No |

Rules live in config, not code, so Prime Pupil's team can edit them.

### Decisions
- **Entry:** support both. **Primary: career-page form triggers the first text** (fixes slow first response). Secondary: texting DRIVE also creates a candidate (demo-friendly). Production would register the web form as an opt-in method.
- **Answers:** free text interpreted by the AI; numbered hints where helpful.
- **Nudge cadence:** day 1, day 2, day 4 → recruiter task on day 5. Appointments: day before + morning of. Quiet hours: no texts before 8am or after 8pm.
- **Tone:** short (aim ≤160 chars), plain language, warm, one ask per message, always clear on next step.

## 12. Recruiter experience (UX)

### Screens
| Screen | Purpose | Contents |
|---|---|---|
| **Today** (home) | "What needs me?" | **Needs you today:** review tasks ranked by urgency, each with reason + one-click actions. **Handled for you:** what the system did today (nudges sent, results processed, candidates advanced), expandable to a log. |
| **Pipeline** | "Where is everyone?" | Stage counts across the top (click to filter) + candidate list: name, depot, stage, status, days in stage, last contact. Filters: depot, recruiter, status. Stuck candidates highlighted. |
| **Candidate detail** | "Why did they stop?" | Progress bar across stages, conversation thread (with English translation under non-English messages), event timeline, step details, actions (approve/reject review, mark dropped with reason). |
| **Demo control panel** (demo only) | Drive the story | Career-page form link, fast-forward X days, simulate vendor events (BG email arrives, drug result, no-show). |

### Recruiter actions
| Task | Actions | What happens |
|---|---|---|
| Screening flag | Approve / Reject (with reason) | Approve → advance + next-step text. Reject → templated message in candidate's language. Both written to Workday (mock). |
| Unresponsive (day 90) | Keep following up / Mark dropped (with reason) | Restart the 90-day schedule, or drop + write to Workday. |
| Other (questions, no consent) | Dismiss | Logged. |

### Follow-up engine
- Runs every 30s (production: scheduler / worker queue). Schedule per stage in config: SMS d1, d2, d4 → AI call d5 → SMS d7, d10, d14 → call d15 → alternating weekly → **day 90: stop, recruiter task.**
- Restarts whenever the candidate replies. Quiet hours 8pm–8am. Never drops or rejects anyone.
- Until voice ships, scheduled calls are logged and sent as texts.
- **Demo clock:** one global simulated offset; "skip ahead" moves time in 6-hour steps, running the engine each step.

### Decisions
- **Home = Today**, because John's #1 pain is recruiters chasing people.
- **Pipeline = stage counts + list**, not kanban: ~600 active candidates would make kanban unusable.
- **Rejections:** recruiter decides; on Reject, the system sends a polite templated message in the candidate's language.
- **Translation:** English translation shown under non-English messages so any recruiter can follow any conversation.
- **Demo controls on a separate page**, so the recruiter UI is the honest product.

## 13. Integrations

| System | In this build | In production |
|---|---|---|
| Twilio SMS | Wired: inbound webhook, outbound send, STOP/START, delivery receipts. Outbound blocked (30034) until A2P approval | Real |
| Vonage WhatsApp (sandbox) / SMS | Adapter: send via Messages API, inbound + status webhooks at /vonage/*, optional JWT signature check | Production WhatsApp sender + registered SMS number |
| Twilio voice | Real: ConversationRelay (ElevenLabs TTS, Deepgram STT) over WebSocket | Same; deploy removes ngrok |
| Claude API | Real | Real |
| Workday: outbound | Outbox → fake Workday `Move_Candidate` (stage steps + dispositions) and `Offer`; hired → Ready for Hire. Step/disposition names mapped in config | Same calls against the tenant (SOAP); IT confirms step and disposition names |
| Background-check vendor | Mock API for ordering; results arrive as emails we parse | Vendor API for ordering (confirm availability); inbound email parsing or vendor webhook for results |
| Drug-test vendor | Mock webhook for results | Vendor's integration (John confirmed one exists) |
| Skills-test platform | Mock webhook for results (Tier 2) | Platform's integration (John confirmed one exists) |
| Workday: inbound (new applicants) | Flag WORKDAY_INTAKE: `poll` = connector polls a fake Workday's `Get_Candidates` every few seconds (default); `direct` = demo posts straight in | Poll the tenant's `Get_Candidates` with a read-only integration account (no build on Prime Pupil's side); push events as an optional upgrade |

## 14. Compliance & guardrails

- Texting consent and opt-out (STOP/START), handled by Twilio and recorded
- Audit trail on every action
- Background-check rejections require a pre-adverse action notice under US law, so they can't be fully automatic

## 15. Risks

| Risk | Mitigation |
|---|---|
| Twilio number registration may not be approved before the demo | Browser chat simulator uses the same logic; fallback to a new trial account with verified numbers |
| Scope is larger than time allows | Build order guarantees a working demo at every stopping point |

## 16. Assumptions log

| Assumption | Why | Status |
|---|---|---|
| Screening questions | — | ✅ Confirmed by John (four automatic fails) |
| BG vendor offers an ordering API | — | ✅ Confirmed by John (integration for orders + results) |
| Facts sheet: pay $24/hr, paid training at same rate | Placeholder so the agent can answer pay questions; clearly marked in config | Confirm with Prime Pupil |
| CDL permit runs in parallel with training; candidate self-reports; recruiter verifies a photo before the offer | John: permit isn't shared during the process, recruiter verifies at the end | Decided |
| Offers are sent via Workday's offer process; we trigger it automatically (Workday Recruiting `Offer` operation) instead of generating our own letter. Our mock e-sign page stands in for it | Terms, templates and approvals stay in Workday; no new work | Assumed (asking John, Q6) |
| Keep Workday synced at every stage (decisions + stage changes), even if recruiters only update it at application and hire | Workday stays accurate with zero double entry | Assumed |
| FCRA adverse-action notices are out of scope | Edge case | Assumed |
| Depots are in upstate NY | Matches the 518 test number; John said one state | Cosmetic |

## 17. Decision log

| Date | Decision | Why |
|---|---|---|
| 11-19 | Goal = cut total time to hire | Drop-off is caused by gaps between steps |
| 11-19 | Python backend, TypeScript frontend | Author's strongest languages; maps to candidate vs. recruiter sides |
| 11-19 | Local first, deploy if time permits | Speed while building; stability for demo |
| 11-19 | Mock Workday connector, not slides-only | IT gets something concrete; real beats polished |
| 11-19 | Rules decide, AI talks | Predictability, auditability, safe edge cases |
| 11-19 | Strict stage sequence; no parallel steps | John: don't pay for later steps early |
| 11-19 | System never rejects; failures → recruiter review task. Offers auto-send. | John's stated policy |
| 11-19 | Career-page application triggers instant first text | Biggest screening delay is slow first response (1–2 wks) |
| 11-19 | Auto-order BG check via mock vendor API | Removes a recruiter step; assumes vendor API (confirm in email 2) |
| 11-19 | Drug test + skills test results via mock vendor webhooks; BG results via email parsing | Matches how John says each vendor delivers results |
| 11-19 | Scope cut: deep on stages 1–3, light on 4–5; voice at end of Tier 1 | Most of the 90 days is lost in screening, BG, drug test |
| 11-19 | Separate stage (where) from status (what's happening) | "Drug test · waiting on candidate" is actionable; powers Needs-you |
| 11-19 | General Step table + detail tables per step (class table inheritance) | Engine logic stays uniform; vendor data gets typed fields that map to vendor payloads |
| 11-19 | Drop-off reason = fixed list + note | Clean totals for VP + detail for recruiters |
| 11-19 | Entry: career-page form triggers first text (primary); DRIVE keyword (secondary) | Matches John's real flow; keyword supports demo + registration |
| 11-19 | Free-text answers interpreted by AI | Natural for candidates; handles mixed language |
| 11-19 | Nudges d1/d2/d4 → recruiter task d5; quiet hours 8am–8pm | Persistent but respectful; humans step in before candidates are lost |
| 11-19 | Recruiter home = Today (Needs you + Handled for you) | John's #1 pain is chasing people |
| 11-19 | Pipeline = counts + list, not kanban | Scales to ~600 active candidates |
| 11-19 | Recruiter decides rejections; system sends templated message in candidate's language | Human judgment, consistent and kind communication |
| 11-19 | Show English translation under non-English messages | Not every recruiter speaks Spanish |
| 11-19 | Demo controls on a separate page | Recruiter UI stays the real product |
| 11-19 | SQLModel + SQLite now; Postgres in production | Least code, reads like the data model; SQLAlchemy underneath; swap is a connection string |
| 11-19 | Conversation = code decides, Claude writes (one structured call per turn; no agent tools) | Predictable, auditable; Claude never advances or rejects anyone |
| 11-19 | Consequential messages (intro, passed, under review) use fixed templates, not AI wording | Exact wording is reviewable by HR/legal; AI handles the conversational parts |
| 11-19 | Claude gets the ordered list of remaining questions; code decides order and completion | Fixed a bug where Claude had nothing to ask after an answer |
| 11-19 | Voice: turn-based first (Twilio speech recognition + same screening logic), then streaming (ConversationRelay) for the demo | Get a working real-phone path fast; streaming is the natural-sounding experience Alex expects |
| 11-19 | Turn-based voice tested and rejected (robotic, slow); switched to Twilio ConversationRelay with ElevenLabs voice + Deepgram (auto EN/ES detection) | Natural turn-taking + interruptions; Twilio stays the telephony layer; same conversation brain |
| 11-19 | Assistant is stage-aware beyond screening (BG + drug test): answers questions using the candidate's current step; code still decides | Candidates need help at the stages where most time is lost |
| 11-19 | Mock vendor pages the candidate can tap (BG form, drug test authorization + booking) | Interactive demo; mirrors real vendor-hosted pages |
| 11-19 | BG results arrive as emails parsed by Claude (demo: one-click sample email; prod: inbound-email webhook matched by order ID) | Matches John: results come by email |
| 11-19 | (superseded) Drug test booked appointments | — |
| 11-19 | Drug test is a walk-in (John: "take it to any clinic in their network"): we text the authorization + clinics and ask when they'll go; Claude extracts the day/time (with a 7-day calendar), code saves the plan; reminders day before + morning of; no sample by next day → "when would work better?" | Matches John's process and turns the step into a conversation |
| 11-19 | Overdue results (5 days) are an FYI flag to the recruiter, not a required action | Visibility without adding work (to revisit) |
| 11-19 | Permit proof: candidate texts a photo; Claude reads it (name, number, class, expiry) and flags mismatches; recruiter verifies with one click, at upload (before paid training) | Catches problems before Prime Pupil pays for training; how they verify today is an open question (Q18) |
| 11-19 | Training: weekly cohort (next Monday), Zoom link + session reminders; trainer marks complete | No info on completion tracking; Zoom attendance integration is the production story |
| 11-19 | Skills test via mock platform webhook; fail → recruiter review (retest or reject) | John: platform offers an integration |
| 11-19 | Offer auto-generated from template (placeholder terms), mock e-sign; signed → hired, synced to Workday | John: offers can go out automatically |
| 11-19 | VP Insights tab: funnel, days per stage, hires vs baseline/goal, why/where candidates stopped, by depot, automation share | VP is the decision maker: "speed and volume across all locations" |
| 11-19 | Insights filters (date, language, channel, status, depot, recruiter) + weekly trend + click-through to Pipeline | VP slices by what matters; Director of Recruiting can act on any number |
| 11-19 | Value panels: speed to first contact (measured), recruiter hours saved (automated actions × editable minutes), what-if to hit 35 hires (sliders on real funnel pass rates); sortable charts | Show value with visible, editable assumptions; no invented outcomes |
| 11-19 | Weekly trend is clickable (filter dashboard to that week's applicants, or open that week's applicants/hires); sortable depot table with conversion, time to hire, stuck, lowest converters highlighted; ⓘ definitions on every metric | Drill from a number to the people behind it; prevent misreads |
| 11-19 | Demo data: ~1,500 candidates / 150 days (steady-state trend, no warm-up ramp) / 12 depots, fictional 555-01XX numbers (never texted or called), labeled illustrative, tuned to modest results | Show scale without fabricating an improvement claim |
| 11-19 | CDL is parallel, not strict: training starts after the drug test; permit reminders run alongside and stop when the candidate says they have it ("your recruiter will ask before your offer") | Matches John's process; permit wait no longer blocks training |
| 11-19 | Permit: match their process. Requested and verified at the end, as a recruiter review before the offer can go out | Some steps need a human; the system tees them up instead of bypassing them |
| 11-19 | BG results via vendor integration; email parsing kept as fallback | John: vendor integration covers results |
| 11-19 | Training completion: watch the trainer's shared spreadsheet; marking complete moves the candidate on automatically | Trainer's workflow unchanged; removes "recruiters check when they remember" |
| 11-19 | Screening = John's four automatic fails (21+, licensed 3+ yrs, no DUI in 7 yrs, willing to drug test); failures still go to recruiter review | Match their process; John earlier said a recruiter reviews before any rejection |
| 11-19 | On calls, links never get read aloud: anything with a link goes by text (WhatsApp/SMS) and the call says "I just texted you the link for your next step" | Reading URLs aloud is unusable |
| 11-19 | UI refresh (option A: consistent, calm): friendly event labels everywhere; Today with per-recruiter queue; Pipeline search/sort/paging (permit not a separate stage); candidate page with header, progress bar + permit side track, tabbed step details, filtered timeline; demo split into career-page New applicant, candidate-centric console, Workday page; Spanish-formatted dates | Clarity for the panel; product vs. demo props clearly separated |
| 11-19 | Recruiter Settings page: follow-up schedules per stage, give-up day, quiet hours, AI calls on/off; message wording (EN/ES, preview, reset); screening thresholds; stuck/overdue time limits. Overrides on top of defaults; guardrails keep placeholders and SMS opt-out. No roles/history for the demo | Recruiting team controls the system without engineers |
| 11-19 | Workday writes via a transactional outbox: queued in the same save as the change, delivered after commit, retried on every engine tick | Workday slow/down never blocks a candidate; nothing lost |
| 11-19 | Workday intake: poll `Get_Candidates` (production approach) with a fake Workday in the demo; direct-post shortcut kept behind a flag | Lowest lift for IT (read-only account, nothing to build on their side) |
| 11-19 | Messaging providers configurable per channel (SMS_PROVIDER / WHATSAPP_PROVIDER = twilio or vonage); WhatsApp via Vonage Messages API sandbox (Twilio's sandbox unavailable on new accounts); voice stays on Twilio | Swap vendors without touching conversation logic; Vonage sandbox needs no WhatsApp Business account |
| 11-19 | (superseded) Real-phone texting for the demo via WhatsApp (Twilio sandbox); SMS stays wired for when approval lands; trial account as fallback; voice on our number | Carrier approval may not arrive; John suggested WhatsApp; widely used by Spanish-speaking workers |
| 11-19 | Voice turns use Claude Haiku 5.5 (SMS stays on Sonnet 5.5); 0.5s merge window for split utterances | Live calls need ~2s replies; code still makes every decision, so the smaller model is safe |
| 11-19 | Voice both outbound (follow-up calls, "call me now") and inbound | One conversation brain across SMS, voice, and simulator |
| 11-19 | Unknown inbound callers get a polite close (no DRIVE prompt) | Applications come through Workday |
| 11-19 | Calls disclose they're automated; no audio recording, transcript stored as messages | Compliance + one thread per candidate for recruiters |
| 11-19 | Approve/reject happens in our dashboard and syncs to Workday (mock) | One place for recruiters to act; Workday stays system of record |
| 11-19 | Follow-ups run for 90 days (configurable), mixing SMS and AI voice calls; at day 90 reminders stop and a recruiter decides | Solve drop-off by never abandoning candidates early; humans only step in at the end |
| 11-19 | Unresponsive candidates get AI calls, not recruiter calls | Recruiter time is the bottleneck John named |
| 11-19 | "Talk to a person" handoff is out of scope (no recruiter reply box) | Keep focus on automated follow-up |
| 11-19 | Screening tested and accepted; UI polish deferred to the very end | Function first; polish once the flow is complete |
| 11-19 | EN + ES fully supported/tested; other languages answered automatically, untested | Brief priority is Spanish; Claude handles most languages |
| 11-19 | Off-script questions answered only from a configurable facts sheet; otherwise → recruiter task | Claude never invents pay/benefits; placeholders flagged as assumptions |
| 11-19 | Agent confirms back what the candidate said before moving on | Catches misreads; candidate trust |
| 11-19 | Unclear answers: one clarifying question, then flag for recruiter | Never guess on eligibility |
| 11-19 | Start on Claude Sonnet 5.5 (model in config); try Opus 5.5 during testing | Cost while iterating; easy switch |
| 11-19 | New applicants arrive from Workday (mocked "new applicant" event), not our own form | Brief: process runs on Workday; we plug in, not replace |

## 18. Polish backlog

- WhatsApp sequence: user has additional issues to review (handle near the end).

- Voice/SMS conversation sounds repetitive ("Got it… Got it…"). Vary acknowledgments, sound more natural.

## 19. What we'd build next

_TBD_

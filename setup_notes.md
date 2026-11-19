# Setup Notes

## Twilio
- Account upgraded (2026-11-19). Old trial number (+1 737-258-3478) no longer available.
- New number: +1 518-739-7592 — A2P 10DLC campaign SUBMITTED, in review (sole proprietor brand "Nneka Okolo", keyword DRIVE, double opt-in Y). Opt-in/privacy/terms pages in optin-site/.
- Fallback: new trial account (texts verified numbers only, "trial account" prefix).
- Plan: build + test via in-browser chat simulator that hits the same logic as SMS; real SMS only for final checks + demo.
- Auth token: NEVER commit/share; goes in local .env

## Stack (decided)
- Backend: Python + FastAPI + SQLite. Owns Twilio webhooks, stage rules/timers, Claude calls, clinic email parsing, mock Workday connector.
- Frontend: TypeScript + React. Recruiter dashboard + browser chat simulator.
- JSON API between them; for demo, FastAPI serves the built frontend (single deploy).

## Hosting (decided)
- Build locally; ngrok for real-SMS testing.
- Deploy to Render/Railway at the end if time permits (stable demo URL).

"""Demo-only pages and controls sit behind a password (DEMO_PASSWORD). Unset = open (local dev).
Candidate-facing pages (/vendor/*) and Twilio/Vonage/vendor webhooks are never behind it."""

import os
import secrets

from fastapi import Header, HTTPException


def require_demo(x_demo_key: str | None = Header(default=None)) -> None:
    pw = os.getenv("DEMO_PASSWORD", "")
    if pw and not (x_demo_key and secrets.compare_digest(x_demo_key, pw)):
        raise HTTPException(401, "Demo password required")

"""Twilio + public URL plumbing (no business logic here).

- On startup, opens an ngrok tunnel (local dev) so Twilio can reach us, and points the Twilio
  number's voice webhook at it. When deployed, set PUBLIC_URL instead and ngrok is skipped.
- place_call() starts an outbound AI call.
"""

import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

PUBLIC_URL: Optional[str] = os.getenv("PUBLIC_URL")
_client = None


def twilio_ready() -> bool:
    sid, token = os.getenv("TWILIO_ACCOUNT_SID", ""), os.getenv("TWILIO_AUTH_TOKEN", "")
    return sid.startswith("AC") and len(token) > 10 and "paste" not in token


def client():
    global _client
    if _client is None:
        from twilio.rest import Client
        _client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
    return _client


def voice_ready() -> bool:
    return twilio_ready() and bool(PUBLIC_URL)


def start(port: int = 8000) -> None:
    """Open the tunnel (if needed) and point the Twilio number at us. Safe to call when unconfigured."""
    global PUBLIC_URL
    if not PUBLIC_URL:
        # ngrok runs as its own process (see run_tunnel.sh) so app reloads don't drop the tunnel.
        try:
            import json
            import urllib.request
            tunnels = json.load(urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=2))["tunnels"]
            PUBLIC_URL = next(t["public_url"] for t in tunnels if t["public_url"].startswith("https"))
            log.info("ngrok tunnel: %s", PUBLIC_URL)
        except Exception:
            log.warning("No ngrok tunnel found (run ./run_tunnel.sh); voice disabled")
    if voice_ready():
        try:
            number = os.environ["TWILIO_PHONE_NUMBER"]
            nums = client().incoming_phone_numbers.list(phone_number=number, limit=1)
            if nums:
                nums[0].update(voice_url=f"{PUBLIC_URL}/voice/inbound", voice_method="POST")
                log.info("Twilio %s voice webhook -> %s/voice/inbound", number, PUBLIC_URL)
            else:
                log.warning("Twilio number %s not found on this account", number)
        except Exception:
            log.exception("Could not configure Twilio number")


def place_call(to: str, candidate_id: int, reason: str) -> Optional[str]:
    """Start an outbound call. Twilio fetches /voice/answer when it connects. Returns the call SID."""
    if not voice_ready():
        return None
    call = client().calls.create(
        to=to,
        from_=os.environ["TWILIO_PHONE_NUMBER"],
        url=f"{PUBLIC_URL}/voice/answer?candidate_id={candidate_id}&reason={reason}",
        machine_detection="Enable",  # lets us leave a voicemail instead of talking to a machine
    )
    return call.sid


def valid_signature(url: str, params: dict, signature: str) -> bool:
    """Verify a webhook really came from Twilio."""
    from twilio.request_validator import RequestValidator
    return RequestValidator(os.environ["TWILIO_AUTH_TOKEN"]).validate(url, params, signature)

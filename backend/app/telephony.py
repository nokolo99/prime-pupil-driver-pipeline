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


def is_fictional(number: str) -> bool:
    """555-0100..0199 is reserved for fiction in every US area code. Demo data uses it; never dial or text it."""
    import re
    return bool(re.fullmatch(r"\+1\d{3}55501\d{2}", number or ""))


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
    """Find our public URL and (only where allowed) point the Twilio number at us.

    PUBLIC_URL set explicitly (prod) wins; in dev we read it from the local ngrok agent.
    TWILIO_CLAIM_NUMBER controls whether this instance repoints the number's webhooks to itself.
    A phone number forwards to ONE address, so only one instance should claim it (default: prod yes, dev no)."""
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
    claim = os.getenv("TWILIO_CLAIM_NUMBER", "true" if os.getenv("APP_ENV", "dev") == "prod" else "false").lower() == "true"
    if voice_ready() and not claim:
        log.info("Not repointing the Twilio number (TWILIO_CLAIM_NUMBER=false). Calls/texts go wherever it points now.")
    if voice_ready() and claim:
        try:
            number = os.environ["TWILIO_PHONE_NUMBER"]
            nums = client().incoming_phone_numbers.list(phone_number=number, limit=1)
            if nums:
                nums[0].update(voice_url=f"{PUBLIC_URL}/voice/inbound", voice_method="POST",
                               sms_url=f"{PUBLIC_URL}/sms/inbound", sms_method="POST")
                log.info("Twilio %s webhooks -> %s/voice/inbound, /sms/inbound", number, PUBLIC_URL)
            else:
                log.warning("Twilio number %s not found on this account", number)
        except Exception:
            log.exception("Could not configure Twilio number")


def place_call(to: str, candidate_id: int, reason: str) -> Optional[str]:
    """Start an outbound call. Twilio fetches /voice/answer when it connects. Returns the call SID."""
    if not voice_ready() or is_fictional(to):
        return None
    call = client().calls.create(
        to=to,
        from_=os.environ["TWILIO_PHONE_NUMBER"],
        url=f"{PUBLIC_URL}/voice/answer?candidate_id={candidate_id}&reason={reason}",
        # Voicemail detection runs in the background so the agent speaks immediately on answer;
        # if it turns out to be a machine, /voice/amd switches the call to our voicemail message.
        machine_detection="Enable",
        async_amd="true",
        async_amd_status_callback=f"{PUBLIC_URL}/voice/amd?candidate_id={candidate_id}&reason={reason}",
        async_amd_status_callback_method="POST",
    )
    return call.sid


def valid_signature(url: str, params: dict, signature: str) -> bool:
    """Verify a webhook really came from Twilio."""
    from twilio.request_validator import RequestValidator
    return RequestValidator(os.environ["TWILIO_AUTH_TOKEN"]).validate(url, params, signature)


def send_sms(to: str, body: str) -> Optional[str]:
    """Send a text. Returns the message SID. Delivery status arrives later at /sms/status."""
    if not twilio_ready() or is_fictional(to):
        return None
    kwargs = {"to": to, "from_": os.environ["TWILIO_PHONE_NUMBER"], "body": body}
    if PUBLIC_URL:
        kwargs["status_callback"] = f"{PUBLIC_URL}/sms/status"
    return client().messages.create(**kwargs).sid


def send_whatsapp(to: str, body: str) -> Optional[str]:
    """Send a WhatsApp message (Twilio sandbox for the demo). Same Messages API as SMS, with whatsapp: addresses."""
    if not twilio_ready() or is_fictional(to):
        return None
    kwargs = {"to": f"whatsapp:{to}", "from_": os.getenv("WHATSAPP_FROM", "whatsapp:+14155238886"), "body": body}
    if PUBLIC_URL:
        kwargs["status_callback"] = f"{PUBLIC_URL}/sms/status"
    return client().messages.create(**kwargs).sid

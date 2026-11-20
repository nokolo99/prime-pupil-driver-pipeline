"""Messaging providers behind one interface.

The rest of the system calls send_text(channel, to, body). Which company actually delivers it is
configuration, per channel (SMS_PROVIDER / WHATSAPP_PROVIDER = twilio | vonage), so providers can
be swapped without touching conversation logic. Voice is separate and always uses Twilio.
"""

import logging
import os
from typing import Optional

from . import telephony

log = logging.getLogger(__name__)


def provider_for(channel: str) -> str:
    return os.getenv(f"{channel.upper()}_PROVIDER", "twilio").lower()


def send_text(channel: str, to: str, body: str) -> Optional[str]:
    """Deliver an outbound text on 'sms' or 'whatsapp'. Returns the provider's message ID."""
    if telephony.is_fictional(to):
        return None
    if provider_for(channel) == "vonage":
        return vonage_send(channel, to, body)
    return telephony.send_whatsapp(to, body) if channel == "whatsapp" else telephony.send_sms(to, body)


# ---------- Vonage Messages API ----------

def vonage_ready() -> bool:
    k, s = os.getenv("VONAGE_API_KEY", ""), os.getenv("VONAGE_API_SECRET", "")
    return bool(k and s and "paste" not in k and "paste" not in s)


def _vonage_base() -> str:
    sandbox = os.getenv("VONAGE_SANDBOX", "true").lower() == "true"
    return "https://messages-sandbox.nexmo.com/v1/messages" if sandbox else "https://api.nexmo.com/v1/messages"


def vonage_send(channel: str, to: str, body: str) -> Optional[str]:
    import httpx2 as httpx
    if not vonage_ready():
        log.warning("Vonage not configured; message to %s not sent", to)
        return None
    sender = os.getenv("VONAGE_WHATSAPP_FROM" if channel == "whatsapp" else "VONAGE_SMS_FROM", "")
    payload = {"message_type": "text", "text": body, "to": to.lstrip("+"), "from": sender.lstrip("+"), "channel": channel}
    r = httpx.post(_vonage_base(), json=payload, auth=(os.environ["VONAGE_API_KEY"], os.environ["VONAGE_API_SECRET"]), timeout=15)
    if r.status_code >= 300:
        raise RuntimeError(f"Vonage {r.status_code}: {r.text[:200]}")
    return r.json().get("message_uuid")


def vonage_valid_webhook(auth_header: str) -> bool:
    """Vonage signs Messages webhooks with a JWT (HS256, signature secret). Skip if no secret configured."""
    secret = os.getenv("VONAGE_SIGNATURE_SECRET", "")
    if not secret:
        return True
    try:
        import jwt
        jwt.decode(auth_header.removeprefix("Bearer ").strip(), secret, algorithms=["HS256"])
        return True
    except Exception:
        return False


def vonage_download(url: str) -> bytes:
    import httpx2 as httpx
    r = httpx.get(url, auth=(os.environ["VONAGE_API_KEY"], os.environ["VONAGE_API_SECRET"]), follow_redirects=True, timeout=20)
    r.raise_for_status()
    return r.content

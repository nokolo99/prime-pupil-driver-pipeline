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


def enabled() -> bool:
    """MESSAGING_ENABLED=false (e.g. the laptop while prod is live): record messages, never send real ones."""
    return os.getenv("MESSAGING_ENABLED", "true").lower() == "true"


def send_text(channel: str, to: str, body: str) -> Optional[str]:
    """Deliver an outbound text on 'sms' or 'whatsapp'. Returns the provider's message ID."""
    if telephony.is_fictional(to) or not enabled():
        return None
    if provider_for(channel) == "vonage":
        return vonage_send(channel, to, body)
    return telephony.send_whatsapp(to, body) if channel == "whatsapp" else telephony.send_sms(to, body)


# ---------- Vonage Messages API ----------

def vonage_ready() -> bool:
    k, s = os.getenv("VONAGE_API_KEY", ""), os.getenv("VONAGE_API_SECRET", "")
    return bool(k and s and "paste" not in k and "paste" not in s)


def _vonage_base(channel: str) -> str:
    # The sandbox only covers WhatsApp/Messenger/Viber; SMS always uses the real Messages API.
    sandbox = os.getenv("VONAGE_SANDBOX", "true").lower() == "true" and channel != "sms"
    return "https://messages-sandbox.nexmo.com/v1/messages" if sandbox else "https://api.nexmo.com/v1/messages"


import threading
import time

_vonage_lock = threading.Lock()
_vonage_last = [0.0]
VONAGE_MIN_GAP_S = 1.0   # sandbox allows ~1 message/second; we often send 2-3 in a row at stage changes


class PermanentSendError(RuntimeError):
    """The provider refused for good (quota used up, bad number, bad credentials): retrying won't help."""


def _vonage_auth() -> dict:
    """Real WhatsApp senders need a JWT signed with the Vonage application's private key; the sandbox
    accepts the API key/secret. The key comes from a file (laptop / Render secret file) or an env var."""
    app_id = os.getenv("VONAGE_APPLICATION_ID", "")
    key = os.getenv("VONAGE_PRIVATE_KEY", "").replace("\\n", "\n")
    path = os.getenv("VONAGE_PRIVATE_KEY_PATH", "")
    if not key and path and os.path.exists(path):
        key = open(path).read()
    if app_id and key:
        import uuid
        import jwt
        t = int(time.time())
        token = jwt.encode({"application_id": app_id, "iat": t, "exp": t + 300, "jti": str(uuid.uuid4())}, key, algorithm="RS256")
        return {"headers": {"Authorization": f"Bearer {token}"}}
    return {"auth": (os.environ["VONAGE_API_KEY"], os.environ["VONAGE_API_SECRET"])}


def vonage_send(channel: str, to: str, body: str) -> Optional[str]:
    """Send via Vonage, paced to the rate limit (the lock keeps messages in order). Stays quick on purpose:
    one short retry on a real rate limit, and permanent refusals fail at once. Anything that still fails
    is retried by the engine's tick, never by waiting here."""
    import httpx2 as httpx
    if not vonage_ready():
        log.warning("Vonage not configured; message to %s not sent", to)
        return None
    sender = os.getenv("VONAGE_WHATSAPP_FROM" if channel == "whatsapp" else "VONAGE_SMS_FROM", "")
    payload = {"message_type": "text", "text": body, "to": to.lstrip("+"), "from": sender.lstrip("+"), "channel": channel}
    with _vonage_lock:
        for attempt in range(2):
            wait = VONAGE_MIN_GAP_S - (time.monotonic() - _vonage_last[0])
            if wait > 0:
                time.sleep(wait)
            r = httpx.post(_vonage_base(channel), json=payload, timeout=15, **_vonage_auth())
            _vonage_last[0] = time.monotonic()
            if r.status_code == 429 and "limit" in r.text.lower() and "month" in r.text.lower():
                raise PermanentSendError(f"Vonage 429: {r.text[:200]}")  # sandbox monthly quota used up
            if r.status_code == 429:
                time.sleep(1.0)
                continue
            if 400 <= r.status_code < 500:
                raise PermanentSendError(f"Vonage {r.status_code}: {r.text[:200]}")
            if r.status_code >= 300:
                raise RuntimeError(f"Vonage {r.status_code}: {r.text[:200]}")
            return r.json().get("message_uuid")
    raise RuntimeError("Vonage 429: rate-limited")


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

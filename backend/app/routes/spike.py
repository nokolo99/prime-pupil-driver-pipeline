"""Dev-only voice lineup spike: one call that plays each candidate ElevenLabs voice back to back.

Each voice gets its own <Language> code, so tagging a text token with that code picks the voice.
Mounted only when APP_ENV=dev. Not part of the product.
"""

import asyncio
import json
import os
import secrets
from xml.sax.saxutils import quoteattr

from fastapi import APIRouter, WebSocket
from fastapi.responses import Response

from .. import telephony

router = APIRouter(prefix="/spike", tags=["spike"])

MODEL = "-v4"  # same model suffix the real calls use
EN = "Hi Maria! I'm calling about your bus driver application with Prime Pupil. Have you had a DUI in the past seven years? Great. Training starts Monday at ten a.m. at the North Valley depot."
ES = "¡Hola María! Te llamo por tu solicitud de conductor con Prime Pupil. ¿Has tenido un DUI en los últimos siete años? Perfecto. La capacitación empieza el lunes a las diez de la mañana en el depósito de North Valley."
LINEUP = [  # (language code used only to pick the voice, voice id, what it says)
    ("en-US", "8DzKSPdgEQPaK5vKG0Rs", "English voice one. " + EN),
    ("en-GB", "TPbSfDVirzpiSkim8gMw", "English voice two. " + EN),
    ("en-AU", "db0e7kB1Ok43TcwAEuyl", "English voice three. " + EN),
    ("es-US", "MbMvLOFbicjtQwgx0j2r", "Voz en español, número uno. " + ES),
    ("es-MX", "13VFWfJ7e20fmvmaqXWl", "Voz en español, número dos. " + ES),
    ("es-ES", "rixsIpPlTphvsJd2mI03", "Voz en español, número tres. " + ES),
]
KEY_FILE = os.getenv("SPIKE_KEY_FILE", "/private/tmp/claude-501/-Users-nnekaokolo-Documents-Job-Search-Alex/d73ee744-b8fe-41ed-91b1-2ac3a437038d/scratchpad/spike_key.json")
_tokens: dict[str, list] = {}  # call token -> the lineup for that call


@router.post("/voices/call")
def call(to: str, blind_es: bool = False, blind_pairs: bool = False):
    """blind_es: only the Spanish voices, shuffled, labeled A/B/C. The key is written to a file, not returned."""
    lineup = LINEUP
    if blind_es:
        import random
        es = random.sample([x for x in LINEUP if x[0].startswith("es")], 3)
        lineup = [(code, v, f"Opción {'ABC'[i]}. " + ES) for i, (code, v, _) in enumerate(es)]
        key = {f"Opción {'ABC'[i]}": f"Spanish voice {[x[1] for x in LINEUP].index(v) - 2} ({v})" for i, (_, v, _) in enumerate(es)}
        open(KEY_FILE, "w").write(json.dumps(key, indent=1))
    if blind_pairs:
        import random
        en1 = LINEUP[0]
        es = random.sample([LINEUP[3], LINEUP[4]], 2)  # Spanish voices 1 and 2
        lineup = []
        for i, (code, v, _) in enumerate(es):
            lineup += [(en1[0], en1[1], f"Pair {'AB'[i]}. " + EN), (code, v, ES)]
        key = {f"Pair {'AB'[i]}": f"English 1 + Spanish voice {[x[1] for x in LINEUP].index(v) - 2} ({v})" for i, (_, v, _) in enumerate(es)}
        open(KEY_FILE, "w").write(json.dumps(key, indent=1))
    tok = secrets.token_urlsafe(12)
    _tokens[tok] = lineup
    c = telephony.client().calls.create(to=to, from_=os.environ["TWILIO_PHONE_NUMBER"],
                                        url=f"{telephony.PUBLIC_URL}/spike/voices/twiml?token={tok}")
    return {"call_sid": c.sid}


@router.post("/voices/twiml")
def twiml(token: str):
    lineup = _tokens.get(token, LINEUP)
    ws = telephony.PUBLIC_URL.replace("https://", "wss://") + f"/spike/voices/ws?token={token}"
    langs = "".join(f'<Language code="{code}" ttsProvider="ElevenLabs" voice="{v}{MODEL}" '
                    f'transcriptionProvider="Deepgram" />' for code, v, _ in lineup)
    code, v, _ = lineup[0]
    body = ('<?xml version="1.0" encoding="UTF-8"?><Response><Connect>'
            f'<ConversationRelay url={quoteattr(ws)} interruptible="none" transcriptionLanguage="multi" '
            f'transcriptionProvider="Deepgram" ttsLanguage="{code}" ttsProvider="ElevenLabs" voice="{v}{MODEL}">'
            f'{langs}</ConversationRelay></Connect></Response>')
    return Response(body, media_type="application/xml")


@router.websocket("/voices/ws")
async def ws(sock: WebSocket, token: str):
    if token not in _tokens:
        await sock.close(code=4401)
        return
    lineup = _tokens.pop(token)
    await sock.accept()
    async def play():
        for code, _, text in lineup:
            await sock.send_text(json.dumps({"type": "text", "token": text, "last": True, "lang": code,
                                             "interruptible": False, "preemptible": False}))
            await asyncio.sleep(len(text) / 14 + 1.5)  # rough speaking time, plus a short gap
        await asyncio.sleep(3)
        await sock.send_text(json.dumps({"type": "end"}))
    task = None
    try:
        while True:
            msg = json.loads(await sock.receive_text())
            if msg.get("type") == "setup" and task is None:
                task = asyncio.create_task(play())
            elif msg.get("type") == "error":
                print("spike relay error:", msg)
    except Exception:
        if task:
            task.cancel()

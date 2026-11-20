"""FastAPI app entry point."""

from contextlib import asynccontextmanager

import logging

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logging.getLogger("twilio.http_client").setLevel(logging.WARNING)

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from .db import init_db  # noqa: E402
import asyncio  # noqa: E402

from sqlmodel import Session  # noqa: E402

from . import clock  # noqa: E402
from .db import engine as db_engine  # noqa: E402
from .engine import tick  # noqa: E402
from .models import Setting  # noqa: E402
from . import telephony  # noqa: E402
from .routes import (actions, candidates, chat, demo, insights, intake, mock_workday, settings_api, sms,  # noqa: E402
                     vendor, voice, vonage)
from .seed import seed_reference_data  # noqa: E402


def _tick_once() -> None:
    with Session(db_engine) as s:
        tick(s)


def _poll_workday_once() -> None:
    from .workday import poll_new_applicants
    with Session(db_engine) as s:
        poll_new_applicants(s)


async def _workday_poll_loop() -> None:
    """Touchpoint 1: poll Workday for new applicants (only when WORKDAY_INTAKE=poll)."""
    import os
    while True:
        try:
            await asyncio.to_thread(_poll_workday_once)
        except Exception:
            logging.exception("workday poll failed")
        await asyncio.sleep(float(os.getenv("WORKDAY_POLL_SECONDS", "5")))


async def _tick_loop() -> None:
    """Runs the stage engine every 30 seconds. (Production: a scheduler / worker queue.)"""
    while True:
        try:
            await asyncio.to_thread(_tick_once)
        except Exception:
            logging.exception("tick failed")
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_reference_data()
    with Session(db_engine) as s:  # restore the demo clock across restarts
        row = s.get(Setting, "clock_offset_days")
        clock.set_offset(float(row.value) if row else 0)
    await asyncio.to_thread(telephony.start)
    task = asyncio.create_task(_tick_loop())
    poller = asyncio.create_task(_workday_poll_loop())
    yield
    task.cancel()
    poller.cancel()


app = FastAPI(title="Prime Pupil Driver Pipeline", lifespan=lifespan)

import os  # noqa: E402

APP_ENV = os.getenv("APP_ENV", "dev")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server (prod serves the frontend from this same app)
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(candidates.router)
app.include_router(chat.router)
app.include_router(intake.router)
app.include_router(actions.router)
app.include_router(demo.router)
app.include_router(voice.router)
app.include_router(sms.router)
app.include_router(vendor.router)
app.include_router(insights.router)
app.include_router(vonage.router)
app.include_router(mock_workday.router)
app.include_router(settings_api.router)


@app.get("/api/health")
def health():
    from . import telephony
    return {"ok": True, "env": APP_ENV, "public_url": telephony.PUBLIC_URL}


# ---------- Prod: serve the built frontend (frontend/dist) from this app ----------
from pathlib import Path  # noqa: E402

from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

DIST = Path(os.getenv("FRONTEND_DIST", Path(__file__).resolve().parents[2] / "frontend" / "dist"))
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        """Any non-API route returns the React app (client-side routing handles the rest)."""
        f = DIST / path
        return FileResponse(f if path and f.is_file() else DIST / "index.html")

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
from .routes import actions, candidates, chat, demo, intake, voice  # noqa: E402
from .seed import seed_reference_data  # noqa: E402


def _tick_once() -> None:
    with Session(db_engine) as s:
        tick(s)


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
    yield
    task.cancel()


app = FastAPI(title="Prime Pupil Driver Pipeline", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(candidates.router)
app.include_router(chat.router)
app.include_router(intake.router)
app.include_router(actions.router)
app.include_router(demo.router)
app.include_router(voice.router)


@app.get("/api/health")
def health():
    return {"ok": True}

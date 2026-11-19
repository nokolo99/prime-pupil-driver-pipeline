"""FastAPI app entry point."""

from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from .db import init_db  # noqa: E402
from .routes import candidates, chat  # noqa: E402
from .seed import seed_reference_data  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_reference_data()
    yield


app = FastAPI(title="Prime Pupil Driver Pipeline", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(candidates.router)
app.include_router(chat.router)


@app.get("/api/health")
def health():
    return {"ok": True}

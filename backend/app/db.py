"""Database connection. SQLite for the prototype; swap the URL for Postgres in production."""

import os

from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./primepupil.db")

engine = create_engine(
    DATABASE_URL,
    # SQLite: wait for locks instead of failing (the engine's background tick and web requests both write).
    connect_args={"check_same_thread": False, "timeout": 30} if DATABASE_URL.startswith("sqlite") else {},
)

if DATABASE_URL.startswith("sqlite"):
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")   # readers don't block the writer
        cur.execute("PRAGMA busy_timeout=30000")
        cur.close()


def init_db() -> None:
    from . import models  # noqa: F401  (registers tables)
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session

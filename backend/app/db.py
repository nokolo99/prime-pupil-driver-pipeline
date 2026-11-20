"""Database connection. SQLite for the prototype; swap the URL for Postgres in production."""

import os

from sqlmodel import Session, SQLModel, create_engine

# Dev: local file. Prod: a file on the persistent disk, e.g. DATABASE_URL=sqlite:////var/data/primepupil.db
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



# Workday outbox: deliver queued writes right after the transaction that queued them commits
# (in a background thread, so the request never waits on Workday). The engine tick retries failures.
from sqlalchemy import event as _sa_event  # noqa: E402
from sqlalchemy.orm import Session as _OrmSession  # noqa: E402


@_sa_event.listens_for(_OrmSession, "after_commit")
def _dispatch_workday(session):
    if session.info.pop("workday_pending", False):
        import threading

        def run():
            from .workday import dispatch_outbox
            dispatch_outbox()
        threading.Thread(target=run, daemon=True).start()

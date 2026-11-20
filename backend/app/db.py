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
    _add_missing_columns()


def _add_missing_columns() -> None:
    """Tiny SQLite migration: add columns that exist in the models but not yet in the database, so deploys
    never require wiping prod data. (Prod on Postgres would use proper migrations, e.g. Alembic.)"""
    if not DATABASE_URL.startswith("sqlite"):
        return
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                ddl = col.type.compile(dialect=engine.dialect)
                default = col.default.arg if col.default is not None and not callable(col.default.arg) else None
                if hasattr(default, "value"):
                    default = default.value
                dflt = "" if default is None else f" DEFAULT {default!r}" if isinstance(default, str) else f" DEFAULT {int(default) if isinstance(default, bool) else default}"
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl}{dflt}'))


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

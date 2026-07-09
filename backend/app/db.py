from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from .config import settings

log = logging.getLogger("db")

engine = create_async_engine(settings.database_url, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yields a request-scoped async DB session."""
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    """Create tables for the local skeleton.

    In production this is replaced by Alembic migrations; for the SQLite MVP
    we just create_all on startup — plus a tiny idempotent ADD COLUMN pass so a
    pre-existing DB picks up new nullable columns without a wipe.
    """
    from . import models  # noqa: F401 — ensure models are registered

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # create_all never ALTERs existing tables; add columns we know are new.
        await _ensure_columns(conn, "raw_messages", {"reply_to_message_id": "INTEGER"})
        await _ensure_columns(conn, "threat_events", {"reply_to_message_id": "INTEGER"})
        await _ensure_columns(conn, "threats", {"target_count": "INTEGER DEFAULT 1"})
        # create_all() only defines this constraint for BRAND NEW tables — a
        # pre-existing raw_messages table needs it added as a unique index. Only
        # succeeds if the data is already duplicate-free (see scripts/dedupe_ingest.py);
        # skip with a warning rather than crash startup if stale dupes remain.
        try:
            await conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_message_source_msgid "
                "ON raw_messages(source_id, message_id)"
            )
        except OperationalError:
            log.warning(
                "could not create uq_raw_message_source_msgid — duplicate "
                "(source_id, message_id) rows still exist; run scripts/dedupe_ingest.py"
            )


async def _ensure_columns(conn, table: str, columns: dict[str, str]) -> None:
    """SQLite-only: ADD COLUMN for any of `columns` (name->type) not yet present."""
    rows = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
    have = {r[1] for r in rows}
    for name, coltype in columns.items():
        if name not in have:
            await conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {coltype}")

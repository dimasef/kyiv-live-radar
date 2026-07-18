"""Tests for app/migrate.py::upgrade_to_head() against real Alembic migrations
(not the create_all() shortcut the other test files use) — the two paths a
real DB can be in at startup: brand new, or pre-existing without Alembic.
"""

from __future__ import annotations

import asyncio

import pytest_asyncio
from alembic import command
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

import app.migrate as migrate
from app.config import settings


@pytest_asyncio.fixture
async def tmp_db(tmp_path, monkeypatch):
    """Points BOTH `app.migrate`'s engine (used for the pre-flight table
    inspection) and `settings.database_url` (read fresh by migrations/env.py
    on every alembic command) at one isolated tmp-file SQLite DB."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'm.db'}"
    monkeypatch.setattr(settings, "database_url", url)
    tmp_engine = create_async_engine(url)
    monkeypatch.setattr(migrate, "engine", tmp_engine)
    yield tmp_engine
    await tmp_engine.dispose()


def _table_names(sync_conn) -> set[str]:
    return set(inspect(sync_conn).get_table_names())


async def _tables(engine) -> set[str]:
    async with engine.connect() as conn:
        return await conn.run_sync(_table_names)


async def _version(engine) -> str:
    async with engine.connect() as conn:
        row = (await conn.exec_driver_sql("SELECT version_num FROM alembic_version")).first()
        return row[0]


async def test_upgrade_empty_db_creates_schema_and_reaches_head(tmp_db):
    assert await _tables(tmp_db) == set()

    await migrate.upgrade_to_head()

    tables = await _tables(tmp_db)
    assert {"districts", "sources", "raw_messages", "notices", "incidents",
            "threats", "threat_events", "threat_axes", "alembic_version"} <= tables
    assert await _version(tmp_db) == "0012"


async def test_upgrade_twice_is_a_noop(tmp_db):
    await migrate.upgrade_to_head()
    await migrate.upgrade_to_head()  # must not raise / re-apply anything
    assert await _version(tmp_db) == "0012"


async def test_preexisting_pre_alembic_db_is_stamped_and_backfilled(tmp_db):
    """A DB that has the 0001-era schema but no `alembic_version` table (what
    every dev/prod DB looked like before Alembic existed) must be stamped to
    the baseline, then upgraded — with `kind`/`closed_reason` correctly
    backfilled from the old, overloaded `status` column."""
    cfg = migrate._config()
    await asyncio.to_thread(command.upgrade, cfg, "0001")

    async with tmp_db.begin() as conn:
        # Simulate "never touched by Alembic" — the old init_db()/create_all
        # path never wrote this table.
        await conn.exec_driver_sql("DROP TABLE alembic_version")
        for status in ("impact", "lost", "destroyed", "tracking"):
            await conn.exec_driver_sql(
                "INSERT INTO threats (created_at, target_type, status, scope, "
                "target_count, corroboration_count, has_conflict, confidence) "
                f"VALUES (datetime('now'), 'shahed', '{status}', 'district', 1, 1, 0, 0.5)"
            )

    assert "alembic_version" not in await _tables(tmp_db)

    await migrate.upgrade_to_head()

    assert await _version(tmp_db) == "0012"
    async with tmp_db.connect() as conn:
        rows = (
            await conn.exec_driver_sql(
                "SELECT status, kind, closed_reason FROM threats ORDER BY id"
            )
        ).fetchall()
    assert rows == [
        ("impact", "impact", None),
        ("lost", "track", "stale"),
        ("destroyed", "track", "destroyed"),
        ("tracking", "track", None),
    ]

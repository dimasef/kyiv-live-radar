"""Alembic-driven schema setup, replacing the old `init_db()` create_all() +
`_ensure_columns()` ad-hoc column patching.

A pre-Alembic DB (created by that old path, dev SQLite or prod Postgres) has
every table but no `alembic_version` — such a DB is `stamp`-ed straight to the
0001 baseline (which reproduces its schema exactly) before `upgrade head` runs
anything newer. A brand new DB has no tables at all and just runs `upgrade
head` from scratch, which creates everything from 0001 through the latest
revision. Either way this is idempotent and safe to call on every startup.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from .db import engine

log = logging.getLogger("migrate")

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_ALEMBIC_INI = _BACKEND_DIR / "alembic.ini"

# The first migration — matches the schema `create_all()` used to produce, so
# a pre-existing DB can be stamped straight to it without replaying DDL.
_BASELINE_REVISION = "0001"


def _config() -> Config:
    return Config(str(_ALEMBIC_INI))


def _inspect_state(sync_conn) -> tuple[bool, bool]:
    """(has_app_tables, has_alembic_version), read via a sync connection —
    Inspector has no async form, so this runs through `conn.run_sync()`."""
    tables = set(inspect(sync_conn).get_table_names())
    return ("threats" in tables, "alembic_version" in tables)


async def upgrade_to_head() -> None:
    async with engine.connect() as conn:
        has_app_tables, has_alembic_version = await conn.run_sync(_inspect_state)

    cfg = _config()
    if has_app_tables and not has_alembic_version:
        log.info(
            "pre-Alembic database detected — stamping baseline (%s) before upgrading",
            _BASELINE_REVISION,
        )
        # alembic's Config/command API is sync and drives its own event loop
        # internally (see migrations/env.py) — run it off-thread so it doesn't
        # collide with the event loop we're already running in (lifespan/CLI).
        await asyncio.to_thread(command.stamp, cfg, _BASELINE_REVISION)

    await asyncio.to_thread(command.upgrade, cfg, "head")

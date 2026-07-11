"""Regression tests for the reprocess wipe.

`_wipe_tracks` must clear EVERY table that the ingest replay rebuilds —
including `notices`. It once wiped threats/events/incidents but not notices, so
every reprocess DUPLICATED all all-clear/summary notices, and a wrong notice
written by older code (e.g. a train-news post mis-read as a "відбій") survived
forever because the current parser never recreates it.
"""

import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.reprocess as reprocess
from app.db import Base
from app.models import Incident, Notice, Threat, ThreatEvent


@pytest_asyncio.fixture
async def wired_db(tmp_path, monkeypatch):
    """A temp DB whose sessionmaker is wired into the reprocess module."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'r.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(reprocess, "SessionLocal", Session)
    yield Session
    await engine.dispose()


async def test_wipe_tracks_also_clears_notices(wired_db):
    Session = wired_db
    async with Session() as s:
        inc = Incident(target_type="ballistic")
        s.add(inc)
        await s.flush()
        s.add(Threat(target_type="ballistic", status="sighting", incident_id=inc.id))
        s.add(Notice(kind="clear", text="🚆 news post mis-read as відбій"))
        s.add(Notice(kind="summary", text="attack recap"))
        await s.commit()

    await reprocess._wipe_tracks()

    async with Session() as s:
        for model in (ThreatEvent, Threat, Incident, Notice):
            n = await s.scalar(select(func.count()).select_from(model))
            assert n == 0, f"{model.__name__} not wiped: {n} rows remain"

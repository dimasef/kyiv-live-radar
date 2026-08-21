"""Seeding must un-say what the gazetteer no longer says.

`seed_districts` only ever inserted and updated, so an entry REMOVED from
`gazetteer.py` stayed in the DB and kept matching. Live on 2026-08-21: a Kyiv
«ТЕЦ» was seeded from a work-in-progress edit and then deleted from the file —
the row survived, and since "тец" had meanwhile become a whole-word alias, its
three-letter name matched on its own, pinning every bare Kyiv «ТЕЦ» onto a plant
the gazetteer had already disowned.
"""
from __future__ import annotations

from datetime import datetime

import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.models import District, Threat, ThreatEvent
from app.seed import _retire_orphan_districts


@pytest_asyncio.fixture
async def session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'t.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()


async def _orphan(session, name_en: str = "Ghost") -> District:
    d = District(name_uk="Привид", name_en=name_en, lat=50.0, lon=30.0, aliases=[])
    session.add(d)
    await session.commit()
    return d


async def test_unused_orphan_is_removed(session):
    ghost = await _orphan(session)
    await _retire_orphan_districts(session)
    assert await session.get(District, ghost.id) is None


async def test_orphan_with_sightings_is_kept(session):
    """History, not a mistake — dropping it would orphan its events and break
    the foreign key. Logged for the operator instead."""
    ghost = await _orphan(session)
    track = Threat(target_type="shahed", status="tracking", target_count=1,
                   created_at=datetime(2026, 8, 21, 12, 0))
    session.add(track)
    await session.commit()
    session.add(ThreatEvent(threat_id=track.id, district_id=ghost.id,
                            event_time=datetime(2026, 8, 21, 12, 0)))
    await session.commit()

    await _retire_orphan_districts(session)
    assert await session.get(District, ghost.id) is not None


async def test_gazetteer_entries_are_untouched(session):
    """The guard that matters: a normal seed must not delete the real gazetteer."""
    from app.gazetteer import DISTRICTS

    session.add_all(
        District(name_uk=d["name_uk"], name_en=d["name_en"], lat=d["lat"], lon=d["lon"],
                 aliases=d.get("aliases", []))
        for d in DISTRICTS
    )
    await session.commit()
    before = await session.scalar(select(func.count()).select_from(District))
    await _retire_orphan_districts(session)
    assert await session.scalar(select(func.count()).select_from(District)) == before

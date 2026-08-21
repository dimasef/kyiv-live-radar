"""The per-channel target-type context has to survive a process restart.

`_recent_type` lives in memory, so a deploy drops it. That was a five-minute
annoyance while the window was five minutes; with `Source.type_inherit_minutes`
it can be thirty, and the loss showed up live the same day it shipped —
2026-08-21 on the northern channel:

    16:49  Новий реактивний з Брянської     type stated
    16:51  На Сеньківку          jet_drone  inherited
    16:57  Хрінівка 2            jet_drone  inherited  (+8 min)
    17:01  На Добрянку/Вербівку  jet_drone  inherited  (+12 min)
    -- restart --
    17:11  На Любеч              unknown    22 minutes into a 30-minute window

`rehydrate_type_context` replays the recent window through the real
`_note_and_inherit_type`, so every rule (suppressor skips, carrier veto,
ballistic-over-generic guard) stays identical rather than being re-derived.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.gazetteer import DISTRICTS
from app.models import District, RawMessage, Source, utcnow
from app.parsing import DistrictMatcher, parse_message
from app.pipeline.ingest import (
    _note_and_inherit_type,
    _recent_type,
    rehydrate_type_context,
)
from app.timeutil import naive

M = DistrictMatcher([{"id": i + 1, **d} for i, d in enumerate(DISTRICTS)])


@pytest_asyncio.fixture
async def session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'t.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        s.add_all(
            District(name_uk=d["name_uk"], name_en=d["name_en"], lat=d["lat"], lon=d["lon"],
                     aliases=d.get("aliases", []), region=d.get("region", "kyiv"),
                     region_only=bool(d.get("region_only", False)))
            for d in DISTRICTS
        )
        await s.commit()
        _recent_type.clear()
        yield s
    _recent_type.clear()
    await engine.dispose()


async def _channel(session, minutes: int | None) -> Source:
    src = Source(channel_key="north", name="North", region="kyiv",
                 type_inherit_minutes=minutes)
    session.add(src)
    await session.commit()
    return src


def _feed(text: str, source_id: int, when, window: int | None):
    parsed = parse_message(text, M)
    _note_and_inherit_type(parsed, source_id, when, window)
    return parsed


async def test_context_is_restored_after_a_restart(session):
    src = await _channel(session, 30)
    now = naive(utcnow())
    session.add(
        RawMessage(source_id=src.id, message_id=1, text="Новий реактивний з Брянської",
                   event_time=now - timedelta(minutes=20))
    )
    await session.commit()

    _recent_type.clear()  # the restart
    assert await rehydrate_type_context(session) == 1
    assert _feed("Троя", src.id, now, 30).target_type == "jet_drone"


async def test_without_rehydration_the_type_is_lost(session):
    """The failure itself, so the fix above is measured against something."""
    src = await _channel(session, 30)
    now = naive(utcnow())
    session.add(
        RawMessage(source_id=src.id, message_id=1, text="Новий реактивний з Брянської",
                   event_time=now - timedelta(minutes=20))
    )
    await session.commit()
    _recent_type.clear()
    assert _feed("Троя", src.id, now, 30).target_type == "unknown"


async def test_messages_older_than_the_window_are_ignored(session):
    src = await _channel(session, 5)
    session.add(
        RawMessage(source_id=src.id, message_id=9, text="Балістика!",
                   event_time=naive(utcnow()) - timedelta(hours=3))
    )
    await session.commit()
    _recent_type.clear()
    assert await rehydrate_type_context(session) == 0


async def test_replay_obeys_the_same_suppressors_as_the_live_path(session):
    """A donation post naming a weapon must not become the channel's type — the
    reason this replays through `_note_and_inherit_type` instead of taking "the
    last message that mentioned a type"."""
    src = await _channel(session, 30)
    now = naive(utcnow())
    session.add_all([
        RawMessage(source_id=src.id, message_id=1, text="Балістика!",
                   event_time=now - timedelta(minutes=20)),
        RawMessage(
            source_id=src.id, message_id=2,
            text="Підтримати проект:\nhttps://send.monobank.ua/jar/2EDJBw6Bv1\n"
                 "Донати тримають проект на плаву! До останнього шахеда.",
            event_time=now - timedelta(minutes=10),
        ),
    ])
    await session.commit()
    _recent_type.clear()
    await rehydrate_type_context(session)
    assert _recent_type[src.id][0] == "ballistic"


@pytest.mark.parametrize("minutes", [0, None])
async def test_channels_with_no_window_are_still_handled(session, minutes):
    """0 disables inheritance for a channel; None means the global default. The
    lookback is the MAX across channels, so neither may crash the replay."""
    src = await _channel(session, minutes)
    session.add(
        RawMessage(source_id=src.id, message_id=1, text="Балістика!",
                   event_time=naive(utcnow()) - timedelta(minutes=1))
    )
    await session.commit()
    _recent_type.clear()
    await rehydrate_type_context(session)  # must not raise

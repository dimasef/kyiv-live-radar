"""A message that reaches us long after it was posted may CLOSE state, never OPEN it.

Telegram hands back history on every reconnect, so a backfill can replay a
message minutes or hours after the fact. Two live failures came from acting on
those as if they were fresh:

* 2026-08-02 — a 00:14 sighting was stored at ~00:28, after its own reply-child
  had already started a track, so it opened a THIRD track plus a brand-new
  incident ~10 s after the відбій: a fresh attack card for a finished attack.
* 2026-07-31 — the 06:53 відбій was ingested before the 05:59 start it belonged
  to, so the end no-op'd and the late start opened an alert nothing could close.
  It hung for two hours and was "dismissed", recording a real alert as a false
  positive.

`enforce_age` is deliberately opt-in (live Telegram only): reprocess and the
replay feed re-run whole old corpora at their own timestamps, where every
message is late by construction.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.gazetteer import DISTRICTS, SOURCES
from app.models import Alert, District, Incident, RawMessage, Source, Threat, utcnow
from app.parsing import DistrictMatcher
from app.pipeline.ingest import ingest_alert_message, ingest_message


@pytest_asyncio.fixture
async def ctx(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'t.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        s.add_all(District(name_uk=d["name_uk"], name_en=d["name_en"], lat=d["lat"],
                           lon=d["lon"], aliases=d.get("aliases", [])) for d in DISTRICTS)
        s.add_all(Source(channel_key=x["channel_key"], name=x["name"],
                         trust_weight=x["trust_weight"]) for x in SOURCES)
        await s.commit()
        districts = list(await s.scalars(select(District)))
        yield s, DistrictMatcher(districts)
    await engine.dispose()


def _late(minutes: int = 45) -> datetime:
    return utcnow() - timedelta(minutes=minutes)


async def _counts(s) -> tuple[int, int]:
    return (
        await s.scalar(select(func.count()).select_from(Threat)),
        await s.scalar(select(func.count()).select_from(Incident)),
    )


async def test_late_sighting_opens_neither_track_nor_incident(ctx):
    s, matcher = ctx
    await ingest_message(
        s, text="2х БПЛА Троєщина", matcher=matcher, when=_late(),
        source_id=1, message_id=1, enforce_age=True,
    )
    assert await _counts(s) == (0, 0)
    # The message itself is never lost — raw storage happens before any of this.
    raw = await s.scalar(select(RawMessage).where(RawMessage.message_id == 1))
    assert raw is not None and raw.processed


async def test_a_fresh_sighting_is_unaffected(ctx):
    s, matcher = ctx
    await ingest_message(
        s, text="2х БПЛА Троєщина", matcher=matcher, when=utcnow(),
        source_id=1, message_id=1, enforce_age=True,
    )
    assert await _counts(s) == (1, 1)


async def test_replay_and_reprocess_paths_keep_working(ctx):
    """Same old message, `enforce_age` off (the default) — the whole replay/
    reprocess corpus is old, so gating it would drop everything."""
    s, matcher = ctx
    await ingest_message(
        s, text="2х БПЛА Троєщина", matcher=matcher, when=_late(),
        source_id=1, message_id=1,
    )
    assert await _counts(s) == (1, 1)


async def test_late_stand_down_still_closes_open_tracks(ctx):
    """The recovery case: re-ingesting the відбій we missed during a dropout is
    exactly why a backfill runs at all."""
    s, matcher = ctx
    await ingest_message(
        s, text="2х БПЛА Троєщина", matcher=matcher, when=utcnow(),
        source_id=1, message_id=1, enforce_age=True,
    )
    await ingest_message(
        s, text="Дорозвідка", matcher=matcher, when=_late(),
        source_id=1, message_id=2, enforce_age=True,
    )
    track = await s.scalar(select(Threat))
    assert track.closed_at is not None
    assert track.closed_reason == "stand_down"


async def test_late_alert_start_is_ignored_but_a_late_end_is_honoured(ctx):
    s, _matcher = ctx
    start = "‼️УВАГА! У Києві оголошена повітряна тривога!"
    end = "❕Відбій повітряної тривоги!"

    await ingest_alert_message(s, text=start, when=_late(), source_id=1, message_id=1,
                               enforce_age=True)
    assert await s.scalar(select(func.count()).select_from(Alert)) == 0

    # A real, live alert — then its відбій arrives late (the 07-31 shape).
    await ingest_alert_message(s, text=start, when=utcnow(), source_id=1, message_id=2,
                               enforce_age=True)
    await ingest_alert_message(s, text=end, when=_late(), source_id=1, message_id=3,
                               enforce_age=True)
    alert = await s.scalar(select(Alert))
    assert alert.ended_at is not None
    assert alert.closed_reason == "official"


async def test_late_alert_start_still_replays_under_reprocess(ctx):
    s, _ = ctx
    await ingest_alert_message(
        s, text="‼️УВАГА! У Києві оголошена повітряна тривога!",
        when=datetime(2026, 7, 31, 5, 59, tzinfo=UTC), source_id=1, message_id=1,
    )
    assert await s.scalar(select(func.count()).select_from(Alert)) == 1

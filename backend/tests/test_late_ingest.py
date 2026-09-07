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

The ALERT channel is gated on supersession rather than on age, and 2026-09-07 is
why: a siren that started 67 minutes before the listener reconnected is still
sounding, and dropping its start left Kyiv painted clear through a red alert.
Only a later ВІДБІЙ invalidates a start — see ingest/alert._stood_down_since.

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
from app.gazetteer import SOURCES
from app.models import Alert, District, Incident, RawMessage, Source, Threat, utcnow
from app.parsing import DistrictMatcher
from app.pipeline.ingest import ingest_alert_message, ingest_message
from tests.conftest import district_rows


@pytest_asyncio.fixture
async def ctx(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'t.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        s.add_all(district_rows())
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


START = "‼️УВАГА! У Києві оголошена повітряна тривога!"
END = "❕Відбій повітряної тривоги!"


async def test_a_still_running_alert_backfilled_late_is_opened(ctx):
    """2026-09-07: the listener reconnected 67 minutes into a live siren, the
    backfill replayed its start, and the age gate threw it away — so the banner
    stayed silent and Kyiv sat clear on the map for the rest of the attack."""
    s, _matcher = ctx
    began = _late(67)
    await ingest_alert_message(s, text=START, when=began, source_id=1, message_id=1,
                               enforce_age=True)
    alert = await s.scalar(select(Alert))
    assert alert is not None and alert.ended_at is None
    # Dated when the siren actually sounded, so the banner shows its true age
    # rather than restarting the clock at the reconnect.
    assert alert.started_at.replace(tzinfo=UTC) == began


async def test_a_start_the_siren_has_already_outlived_is_ignored(ctx):
    """The 07-31 shape: the відбій landed first, so the start it belonged to must
    not open an alert nothing can ever close. The end left no `alerts` row behind
    (there was nothing open to close), which is why this reads the channel's own
    messages rather than the table."""
    s, _matcher = ctx
    await ingest_alert_message(s, text=END, when=_late(30), source_id=1, message_id=1,
                               enforce_age=True)
    await ingest_alert_message(s, text=START, when=_late(90), source_id=1, message_id=2,
                               enforce_age=True)
    assert await s.scalar(select(func.count()).select_from(Alert)) == 0


async def test_a_later_start_does_not_supersede_an_earlier_one(ctx):
    """An escalation is the SAME siren announcing a new level (the channel sounds
    no відбій between threat kinds), so replaying both in order has to give the
    true start time and the current level — not a window that begins at the
    escalation."""
    s, _matcher = ctx
    began = _late(67)
    await ingest_alert_message(s, text="🟡 УВАГА! У Києві оголошена дронова небезпека!",
                               when=began, source_id=1, message_id=1, enforce_age=True)
    await ingest_alert_message(
        s, text="🔴 УВАГА! У Києві оголошена нова загроза — ракетна загроза!",
        when=_late(64), source_id=1, message_id=2, enforce_age=True)
    alert = await s.scalar(select(Alert))
    assert await s.scalar(select(func.count()).select_from(Alert)) == 1
    assert alert.level == "red" and alert.threat == "missile"
    assert alert.started_at.replace(tzinfo=UTC) == began


async def test_a_late_end_is_still_honoured(ctx):
    """The recovery case a backfill exists for: a real siren whose відбій we
    missed during the dropout. Both messages are late — the whole window is —
    and the відбій still has to land, dated when it was posted."""
    s, _matcher = ctx
    ended = _late(45)
    await ingest_alert_message(s, text=START, when=_late(90), source_id=1, message_id=2,
                               enforce_age=True)
    await ingest_alert_message(s, text=END, when=ended, source_id=1, message_id=3,
                               enforce_age=True)
    alert = await s.scalar(select(Alert))
    assert alert.ended_at.replace(tzinfo=UTC) == ended
    assert alert.closed_reason == "official"


async def test_replaying_a_stored_message_repairs_a_state_it_never_wrote(ctx):
    """A backfill re-reads what it already stored, and that is now how a missed
    transition heals: the raw row exists, so the old dedup returned early and the
    alert stayed lost forever. Idempotent, so the repeat writes nothing new."""
    s, _matcher = ctx
    began = _late(67)
    await ingest_alert_message(s, text=START, when=began, source_id=1, message_id=1,
                               enforce_age=True)
    # Wipe what the first pass wrote, keeping the raw message — the shape a
    # vetoed or half-committed pass leaves behind.
    for a in list(await s.scalars(select(Alert))):
        await s.delete(a)
    await s.commit()

    await ingest_alert_message(s, text=START, when=began, source_id=1, message_id=1,
                               enforce_age=True)
    assert await s.scalar(select(func.count()).select_from(Alert)) == 1
    # …and replaying it once more changes nothing.
    await ingest_alert_message(s, text=START, when=began, source_id=1, message_id=1,
                               enforce_age=True)
    assert await s.scalar(select(func.count()).select_from(Alert)) == 1
    assert await s.scalar(select(func.count()).select_from(RawMessage)) == 1


async def test_late_alert_start_still_replays_under_reprocess(ctx):
    s, _ = ctx
    await ingest_alert_message(
        s, text="‼️УВАГА! У Києві оголошена повітряна тривога!",
        when=datetime(2026, 7, 31, 5, 59, tzinfo=UTC), source_id=1, message_id=1,
    )
    assert await s.scalar(select(func.count()).select_from(Alert)) == 1

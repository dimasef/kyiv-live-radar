"""Unit tests for app/lifecycle.py, plus a regression test for the
destroyed-in-the-gap bug it helped surface (see tracking.py::find_open_track's
`gap_minutes` param and ingest.py's destroyed branch)."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.domain.lifecycle import CLOSED_REASON_TO_STATUS, TRACK_TRANSITIONS, close_track, promote_track
from app.gazetteer import DISTRICTS, SOURCES
from app.models import CLOSED_REASONS, District, Source, Threat, THREAT_STATUSES
from app.parsing import DistrictMatcher
from app.pipeline.ingest import ingest_message

BASE = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)


# --- close_track / promote_track ---

def _open_threat() -> Threat:
    return Threat(target_type="shahed", status="tracking")


def test_close_track_sets_closed_at_and_reason():
    t = _open_threat()
    close_track(t, BASE, "destroyed")
    assert t.closed_at == BASE
    assert t.closed_reason == "destroyed"


@pytest.mark.parametrize("reason", CLOSED_REASONS)
def test_close_track_maps_every_reason_to_a_legacy_status(reason):
    # Every closed_reason must map to a real legacy status value, so old
    # API clients / the frontend (which still reads `status`) keep working.
    t = _open_threat()
    close_track(t, BASE, reason)
    assert t.status == CLOSED_REASON_TO_STATUS[reason]
    assert t.status in THREAT_STATUSES


def test_close_track_rejects_unknown_reason():
    with pytest.raises(ValueError):
        close_track(_open_threat(), BASE, "bogus")


def test_promote_track_sets_tracking():
    t = Threat(target_type="shahed", status="unconfirmed")
    promote_track(t)
    assert t.status == "tracking"


def test_transition_table_only_reaches_terminal_or_known_statuses():
    # Sanity check on the documented transition table: every target status is
    # itself a key (terminal states map to no further transitions).
    for status, nexts in TRACK_TRANSITIONS.items():
        assert status in THREAT_STATUSES
        for n in nexts:
            assert n in THREAT_STATUSES


# --- Regression: destroyed-in-the-gap (weak point #2 in the risk map) ---
# A reply-less "знищено" landing 16-19 minutes after the last sighting used to
# find no track to close: find_open_track looked back only track_gap_minutes
# (15) by default, well short of track_stale_minutes (20) — the window during
# which the sweeper still considers the track alive. Fixed by having the
# destroyed branch pass gap_minutes=track_stale_minutes explicitly.

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
        sources = list(await s.scalars(select(Source)))
        matcher = DistrictMatcher(districts)
        yield s, matcher, sources
    await engine.dispose()


async def test_destroyed_in_the_gap_still_closes_the_track(ctx):
    s, m, src = ctx
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    # 17 minutes later: past track_gap_minutes (15, the normal grouping
    # window) but within track_stale_minutes (20, when the sweeper would
    # otherwise still consider it live). No reply, no named district.
    out = await ingest_message(s, text="Збили ✅", matcher=m,
                               when=BASE + timedelta(minutes=17),
                               source_id=src[0].id, message_id=2)
    t = (await s.scalars(select(Threat))).first()
    assert t.status == "destroyed" and t.closed_at is not None
    assert t.closed_reason == "destroyed"
    assert len(out) == 1 and out[0].type == "event"


async def test_destroyed_past_the_stale_window_still_finds_nothing(ctx):
    # Sanity check the fix has a bound: past track_stale_minutes (20) the
    # sweeper itself would already have closed a truly-silent track, so
    # find_open_track correctly finds nothing to close.
    s, m, src = ctx
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    out = await ingest_message(s, text="Збили ✅", matcher=m,
                               when=BASE + timedelta(minutes=25),
                               source_id=src[0].id, message_id=2)
    t = (await s.scalars(select(Threat))).first()
    assert t.status == "tracking" and t.closed_at is None
    assert out == []

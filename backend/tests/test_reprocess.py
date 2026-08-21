"""Regression tests for the reprocess wipe — both the full one and the scoped
"last N messages" one.

`_wipe_tracks` must clear EVERY table that the ingest replay rebuilds —
including `notices`. It once wiped threats/events/incidents but not notices, so
every reprocess DUPLICATED all all-clear/summary notices, and a wrong notice
written by older code (e.g. a train-news post mis-read as a "відбій") survived
forever because the current parser never recreates it.

The scoped wipe has the opposite failure mode: cutting a track in half, leaving
one target on the map as two.
"""

from datetime import datetime, timedelta

import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.pipeline.reprocess as reprocess
from app.db import Base
from app.models import Alert, District, Incident, Notice, RawMessage, Threat, ThreatEvent

T0 = datetime(2026, 8, 18, 20, 0)


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


async def _seed_timeline(Session):
    """Ten messages one minute apart, and a track built from #4 and #8 — i.e. a
    track that STRADDLES a naive "last 5 messages" cutoff."""
    async with Session() as s:
        d = District(name_uk="Тест", name_en="Test", lat=50.45, lon=30.52)
        s.add(d)
        await s.flush()
        for i in range(10):
            s.add(RawMessage(text=f"m{i}", event_time=T0 + timedelta(minutes=i)))
        old = Threat(target_type="shahed", status="tracking")
        straddler = Threat(target_type="shahed", status="tracking")
        s.add_all([old, straddler])
        await s.flush()
        s.add(ThreatEvent(threat_id=old.id, district_id=d.id, raw_text="a",
                          event_time=T0 + timedelta(minutes=1)))
        s.add(ThreatEvent(threat_id=straddler.id, district_id=d.id, raw_text="b",
                          event_time=T0 + timedelta(minutes=4)))
        s.add(ThreatEvent(threat_id=straddler.id, district_id=d.id, raw_text="c",
                          event_time=T0 + timedelta(minutes=8)))
        await s.commit()
        return old.id, straddler.id


async def test_scope_cutoff_snaps_back_to_a_straddling_track(wired_db):
    Session = wired_db
    await _seed_timeline(Session)

    async with Session() as s:
        # Last 5 messages start at minute 5 — but the track's first event is at
        # minute 4, so the cutoff must move back to it rather than split it.
        cutoff = await reprocess.scope_cutoff(s, 5)
    assert cutoff == T0 + timedelta(minutes=4)


async def test_scope_cutoff_snaps_back_to_an_open_alert(wired_db):
    Session = wired_db
    await _seed_timeline(Session)
    async with Session() as s:
        s.add(Alert(scope="city", started_at=T0 + timedelta(minutes=2)))
        await s.commit()

    async with Session() as s:
        cutoff = await reprocess.scope_cutoff(s, 5)
    # An alert that never ended spans everything after it starts.
    assert cutoff == T0 + timedelta(minutes=2)


async def test_wipe_since_keeps_older_history(wired_db):
    Session = wired_db
    old_id, straddler_id = await _seed_timeline(Session)
    async with Session() as s:
        s.add(Notice(kind="clear", text="old", event_time=T0 + timedelta(minutes=1)))
        s.add(Notice(kind="clear", text="new", event_time=T0 + timedelta(minutes=6)))
        await s.commit()

    await reprocess._wipe_since(T0 + timedelta(minutes=4))

    async with Session() as s:
        assert {t.id for t in await s.scalars(select(Threat))} == {old_id}
        # The straddler goes ENTIRELY, both its events with it — a rebuild that
        # left the minute-4 half behind would show one target as two.
        assert await s.scalar(select(func.count()).select_from(ThreatEvent)) == 1
        assert {n.text for n in await s.scalars(select(Notice))} == {"old"}
        # raw_messages are never touched — a reprocess must stay repeatable.
        assert await s.scalar(select(func.count()).select_from(RawMessage)) == 10


async def test_wipe_since_prunes_push_state_without_choking_on_citywide_keys(wired_db):
    # danger_state mixes three key shapes: "<track_id>", "city:<track_id>" and
    # the bare "city_last_push" cooldown stamp. Pruning ran int(key) over all of
    # them, so a scoped reprocess raised ValueError for every subscriber who had
    # ever received a city-wide push — taking the whole rebuild down with it.
    from app.models import PushSubscription

    Session = wired_db
    _, straddler_id = await _seed_timeline(Session)
    async with Session() as s:
        s.add(PushSubscription(
            endpoint="https://push.example/x", p256dh="k", auth="a",
            danger_state={
                str(straddler_id): {"level": 2},
                f"city:{straddler_id}": {"pushed_at": "2026-08-18T20:00:00"},
                "city_last_push": "2026-08-18T20:00:00",
                "999": {"level": 1},
            },
        ))
        await s.commit()

    await reprocess._wipe_since(T0 + timedelta(minutes=4))

    async with Session() as s:
        sub = await s.scalar(select(PushSubscription))
        # Both keys for the deleted track go; the unrelated one and the bare
        # cooldown stamp stay.
        assert set(sub.danger_state) == {"city_last_push", "999"}

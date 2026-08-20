"""Freshness must reach the live map — and only the live map.

`/threats/active` carries `last_event_at`/`stale_at` so the client can fade a
target out as its auto-close approaches. The feed's shallow serialization
deliberately leaves them NULL (a feed row is history, and that path doesn't load
`events`), which also pins the MissingGreenlet trap: touching the lazy
relationship there would raise under async.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base, get_session
from app.main import app
from app.models import District, Threat, ThreatEvent


@pytest_asyncio.fixture
async def client(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'t.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        async def _override():
            yield s

        app.dependency_overrides[get_session] = _override
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, s
        app.dependency_overrides.clear()
    await engine.dispose()


async def _track(
    session, *, target_type="shahed", scope="district", minutes_ago=2, followed=False
) -> Threat:
    """One track with a single sighting `minutes_ago`; `followed=True` adds a
    second sighting that REPLIES to the first, the signal that earns the long
    stale window (see domain/staleness.py)."""
    d = District(name_uk="Дарницький", name_en="Darnytskyi", lat=50.40, lon=30.63)
    session.add(d)
    await session.commit()
    seen = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=minutes_ago)
    th = Threat(
        created_at=seen, target_type=target_type, status="tracking", kind="track", scope=scope
    )
    session.add(th)
    await session.commit()
    session.add(
        ThreatEvent(
            threat_id=th.id, district_id=d.id, raw_text="ціль", event_time=seen,
            decision_source="rule", source_id=1, source_message_id=1,
        )
    )
    if followed:
        session.add(
            ThreatEvent(
                threat_id=th.id, district_id=d.id, raw_text="ціль", event_time=seen,
                decision_source="rule", source_id=1, source_message_id=2,
                reply_to_message_id=1,
            )
        )
    await session.commit()
    return th


async def test_active_threats_publish_the_fade_window(client):
    c, s = client
    await _track(s, minutes_ago=3)
    rows = (await c.get("/threats/active")).json()
    assert len(rows) == 1
    row = rows[0]
    assert row["last_event_at"] is not None and row["stale_at"] is not None
    seen = datetime.fromisoformat(row["last_event_at"])
    stale = datetime.fromisoformat(row["stale_at"])
    # Nobody followed this shahed up, so the fade spans its short window.
    assert (stale - seen) == timedelta(minutes=5)


async def test_a_followed_track_publishes_the_long_window(client):
    """Both axes of the rule have to survive the trip to the client, not just
    the type one — this is what stops a target a channel is actively walking
    along from fading out between its (legitimately spaced) callouts."""
    c, s = client
    await _track(s, target_type="jet_drone", minutes_ago=1, followed=True)
    row = (await c.get("/threats/active")).json()[0]
    seen = datetime.fromisoformat(row["last_event_at"])
    stale = datetime.fromisoformat(row["stale_at"])
    assert (stale - seen) == timedelta(minutes=10)


async def test_freshness_timestamps_carry_an_explicit_utc_offset(client):
    """The trap that a window-length assertion can't see.

    These two fields are ASSIGNED after model_validate, so ThreatOut's `_as_utc`
    validator doesn't run on them — a naive value serializes without an offset,
    and `Date.parse` in the browser then reads it as LOCAL time. On a Kyiv
    client that made a 6-minute-old sighting read as "186 хв тому" (+3 h), while
    the difference between the two fields stayed a correct 20 minutes.
    """
    c, s = client
    await _track(s, minutes_ago=3)
    row = (await c.get("/threats/active")).json()[0]
    for field in ("last_event_at", "stale_at"):
        assert datetime.fromisoformat(row[field]).tzinfo is not None, field
    # And the age read off the wire is the real one, not shifted by a timezone.
    age = datetime.now(UTC) - datetime.fromisoformat(row["last_event_at"])
    assert timedelta(minutes=2) < age < timedelta(minutes=5)


async def test_district_ballistic_fades_on_the_shortest_window(client):
    c, s = client
    await _track(s, target_type="ballistic", minutes_ago=1)
    row = (await c.get("/threats/active")).json()[0]
    seen = datetime.fromisoformat(row["last_event_at"])
    stale = datetime.fromisoformat(row["stale_at"])
    assert (stale - seen) == timedelta(minutes=2)


async def test_citywide_ballistic_keeps_the_normal_window(client):
    c, s = client
    await _track(s, target_type="ballistic", scope="city", minutes_ago=1)
    row = (await c.get("/threats/active")).json()[0]
    seen = datetime.fromisoformat(row["last_event_at"])
    stale = datetime.fromisoformat(row["stale_at"])
    assert (stale - seen) == timedelta(minutes=20)


async def test_feed_rows_omit_freshness_without_touching_lazy_events(client):
    c, s = client
    await _track(s, minutes_ago=1)
    rows = (await c.get("/events/recent")).json()
    assert len(rows) == 1
    assert rows[0]["threat"]["last_event_at"] is None
    assert rows[0]["threat"]["stale_at"] is None


async def test_health_publishes_the_server_clock(client):
    c, _ = client
    body = (await c.get("/health")).json()
    assert "server_time" in body
    # Parseable and sane — this is what the client's clock-skew correction rides on.
    assert abs(
        (datetime.fromisoformat(body["server_time"]) - datetime.now(UTC)).total_seconds()
    ) < 60

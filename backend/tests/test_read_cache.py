"""The hydrate cache must never show a reader a map older than the last write.

One rendered copy per generation of the database; any ORM write bumps the
generation, EXCEPT a presence stamp (users.last_seen_at), which no cached
response contains and which every authenticated poll would otherwise turn
into a full re-render.
"""
from __future__ import annotations

from datetime import UTC, datetime

import app.api.read_cache as read_cache
from app.models import District, Threat, ThreatEvent, User, utcnow


async def _track(session) -> Threat:
    d = District(name_uk="Дарницький", name_en="Darnytskyi", lat=50.40, lon=30.63)
    session.add(d)
    await session.commit()
    seen = datetime.now(UTC).replace(tzinfo=None)
    th = Threat(created_at=seen, target_type="shahed", status="tracking", kind="track")
    session.add(th)
    await session.commit()
    session.add(
        ThreatEvent(
            threat_id=th.id, district_id=d.id, raw_text="ціль", event_time=seen,
            decision_source="rule", source_id=1, source_message_id=1,
        )
    )
    await session.commit()
    return th


async def test_second_identical_read_is_served_from_the_cache(client):
    first = await client.get("/threats/active")
    second = await client.get("/threats/active")
    assert first.headers["x-cache"] == "miss"
    assert second.headers["x-cache"] == "hit"
    assert second.content == first.content


async def test_a_write_invalidates_every_cached_response(client, session):
    assert (await client.get("/threats/active")).json() == []
    assert (await client.get("/events/recent?limit=60")).json() == []
    await _track(session)
    active = await client.get("/threats/active")
    assert active.headers["x-cache"] == "miss"
    assert len(active.json()) == 1
    feed = await client.get("/events/recent?limit=60")
    assert feed.headers["x-cache"] == "miss"
    assert len(feed.json()) == 1


async def test_a_presence_stamp_alone_keeps_the_cache(client, session):
    u = User(email="reader@x.com", role="user")
    session.add(u)
    await session.commit()
    await client.get("/axes/active")
    u.last_seen_at = utcnow()
    await session.commit()
    assert (await client.get("/axes/active")).headers["x-cache"] == "hit"


async def test_query_variants_are_separate_entries(client):
    await client.get("/events/recent?limit=30")
    assert (await client.get("/events/recent?limit=60")).headers["x-cache"] == "miss"
    assert (await client.get("/events/recent?limit=30")).headers["x-cache"] == "hit"
    assert (
        await client.get("/events/recent?limit=30&region=kyiv")
    ).headers["x-cache"] == "miss"


async def test_kill_switch_bypasses_the_cache(client, monkeypatch):
    monkeypatch.setattr(read_cache.settings, "read_cache_enabled", False)
    await client.get("/axes/active")
    assert (await client.get("/axes/active")).headers["x-cache"] == "bypass"


async def test_reference_data_ignores_pipeline_writes(client, session):
    await client.get("/districts")
    await _track(session)
    assert (await client.get("/districts")).headers["x-cache"] == "hit"

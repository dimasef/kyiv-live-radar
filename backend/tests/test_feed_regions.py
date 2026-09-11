"""The event feed can be narrowed to one watched region.

A northern night is mostly Чернігівщина — real targets, but 150 km away and not
what someone watching Kyiv opens the feed for. The filter has to reach the QUERY,
not just the client's render: filtering a page of `limit` rows client-side would
leave a fraction of a feed on exactly the busy night it matters.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models import District, Threat, ThreatEvent


async def _sighting(session, region: str, name_uk: str, minutes_ago: int) -> None:
    d = District(name_uk=name_uk, name_en=name_uk, lat=51.0, lon=30.7, region=region)
    session.add(d)
    await session.commit()
    when = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=minutes_ago)
    th = Threat(
        target_type="shahed", status="tracking", kind="track", scope="district",
        region=region, created_at=when,
    )
    session.add(th)
    await session.commit()
    session.add(
        ThreatEvent(threat_id=th.id, district_id=d.id, raw_text=name_uk, event_time=when,
                    decision_source="rule")
    )
    await session.commit()


async def test_feed_carries_every_region_by_default(client, session):
    c, s = client, session
    await _sighting(s, "kyiv", "Оболонь", 3)
    await _sighting(s, "chernihiv", "Любеч", 2)
    rows = (await c.get("/events/recent")).json()
    assert {r["threat"]["region"] for r in rows} == {"kyiv", "chernihiv"}


async def test_region_narrows_the_feed(client, session):
    c, s = client, session
    await _sighting(s, "kyiv", "Оболонь", 3)
    await _sighting(s, "chernihiv", "Любеч", 2)
    rows = (await c.get("/events/recent?region=kyiv")).json()
    assert [r["threat"]["region"] for r in rows] == ["kyiv"]


async def test_the_limit_is_spent_on_the_region_asked_for(client, session):
    """The reason this lives on the server: with the northern events filling the
    page, a client-side filter would return 1 row out of a limit of 3."""
    c, s = client, session
    for i in range(5):
        await _sighting(s, "chernihiv", f"Село{i}", 10 + i)
    await _sighting(s, "kyiv", "Оболонь", 3)
    await _sighting(s, "kyiv", "Позняки", 2)
    await _sighting(s, "kyiv", "Троєщина", 1)
    rows = (await c.get("/events/recent?region=kyiv&limit=3")).json()
    assert len(rows) == 3
    assert {r["threat"]["region"] for r in rows} == {"kyiv"}


async def test_several_regions_can_be_asked_for_at_once(client, session):
    """Repeating the param is how a reader watching more than one pool keeps the
    page worth `limit` rows without falling back to "everything"."""
    c, s = client, session
    await _sighting(s, "kyiv", "Оболонь", 3)
    await _sighting(s, "chernihiv", "Любеч", 2)
    rows = (await c.get("/events/recent?region=kyiv&region=chernihiv")).json()
    assert {r["threat"]["region"] for r in rows} == {"kyiv", "chernihiv"}


async def test_a_declared_but_empty_region_returns_an_empty_feed(client, session):
    """A region can be declared before it has any coverage. Asking for it is not
    a client error — 'no data yet' must not read as 'your client is broken'."""
    c, s = client, session
    await _sighting(s, "kyiv", "Оболонь", 3)
    r = await c.get("/events/recent?region=sumy")
    assert r.status_code == 200
    assert r.json() == []


async def test_an_unknown_region_is_rejected(client, session):
    c, _ = client, session
    assert (await c.get("/events/recent?region=lviv")).status_code == 422


async def test_every_feed_size_the_settings_drawer_offers_is_accepted(client, session):
    """The cap used to be 200 while the drawer's largest option was 250, so
    choosing it 422'd on every reload — and the client swallowed the error into
    an empty feed. These are frontend prefsSlice.FEED_LIMITS; they must all pass.
    """
    c, _ = client, session
    for size in (30, 60, 120, 250):
        assert (await c.get(f"/events/recent?limit={size}")).status_code == 200, size
    # Still bounded — an unbounded page would let anyone ask for the whole table.
    assert (await c.get("/events/recent?limit=251")).status_code == 422

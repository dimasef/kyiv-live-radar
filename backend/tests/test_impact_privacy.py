"""Impact markers must never be published while an attack is live.

Where a strike landed is battle-damage assessment for whoever launched it, so
the whole live surface — map, feed, attack banner, per-threat lookup — reports
nothing about impacts. They stay in the DB and surface only in the journal,
once the air-raid alert is over. Each test below pins one of those exits.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.serialize import incident_out
from app.db import Base, get_session
from app.main import app
from app.models import Alert, District, Incident, Threat, ThreatEvent


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


async def _district(session, name_uk="Дарницький", name_en="Darnytskyi") -> District:
    d = District(name_uk=name_uk, name_en=name_en, lat=50.40, lon=30.63)
    session.add(d)
    await session.commit()
    return d


async def _threat(session, district, *, kind="track", status="tracking", when=None,
                  target_type="ballistic"):
    when = when or datetime.now(UTC).replace(tzinfo=None)
    th = Threat(
        target_type=target_type, status=status, kind=kind,
        created_at=when, closed_at=when if kind == "impact" else None,
    )
    session.add(th)
    await session.commit()
    ev = ThreatEvent(
        threat_id=th.id, district_id=district.id, raw_text="влучання по будівлі",
        event_time=when,
    )
    session.add(ev)
    await session.commit()
    return th, ev


async def test_impact_is_absent_from_the_live_map(client):
    c, s = client
    d = await _district(s)
    live, _ = await _threat(s, d)
    impact, _ = await _threat(s, d, kind="impact", status="impact")

    r = await c.get("/threats/active")
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()}
    assert live.id in ids
    assert impact.id not in ids


async def test_impact_event_is_absent_from_the_feed(client):
    c, s = client
    d = await _district(s)
    live, live_ev = await _threat(s, d)
    _impact, impact_ev = await _threat(s, d, kind="impact", status="impact")

    r = await c.get("/events/recent")
    assert r.status_code == 200
    event_ids = {e["event"]["id"] for e in r.json()}
    assert live_ev.id in event_ids
    assert impact_ev.id not in event_ids


async def test_impact_events_cannot_be_fetched_by_threat_id(client):
    c, s = client
    d = await _district(s)
    live, _ = await _threat(s, d)
    impact, _ = await _threat(s, d, kind="impact", status="impact")

    assert (await c.get(f"/threats/{live.id}/events")).status_code == 200
    # Not 200-with-empty-list: the district must not be inferable at all.
    assert (await c.get(f"/threats/{impact.id}/events")).status_code == 404


async def test_incident_publishes_no_impact_count_or_impact_districts(client):
    _c, s = client
    hit_only = await _district(s, "Дніпровський", "Dniprovskyi")
    seen = await _district(s, "Оболонський", "Obolonskyi")
    # A one-track shahed attack: notable ONLY because something landed, so the
    # flag proves the impact signal survived the count being zeroed.
    inc = Incident(started_at=datetime(2026, 8, 1, 0, 18),
                   last_activity_at=datetime(2026, 8, 1, 0, 18),
                   target_type="shahed")
    s.add(inc)
    await s.commit()
    track, _ = await _threat(s, seen, target_type="shahed")
    impact, _ = await _threat(s, hit_only, kind="impact", status="impact",
                              target_type="shahed")
    for th in (track, impact):
        th.incident_id = inc.id
    await s.commit()
    await s.refresh(inc, ["threats"])
    for th in inc.threats:
        await s.refresh(th, ["events"])

    out = incident_out(inc, sentinel_district_id=None)
    assert out.track_count == 1
    assert out.impact_count == 0
    # The district that ONLY appears because something landed there is the leak
    # this guards: it must not show up in the attack's district list.
    assert out.district_ids == [seen.id]
    assert out.district_count == 1
    # A hit still makes the attack banner-worthy — the signal survives, the
    # number and the place don't.
    assert out.notable


async def test_journal_hides_todays_impacts_only_while_the_alert_is_open(client):
    c, s = client
    d = await _district(s)
    today = datetime.now(UTC).replace(tzinfo=None)
    await _threat(s, d, kind="impact", status="impact", when=today)
    yesterday = today - timedelta(days=1)
    await _threat(s, d, kind="impact", status="impact", when=yesterday)
    alert = Alert(scope="city", alert_type="air_raid", started_at=today, provider="telegram")
    s.add(alert)
    await s.commit()

    def _impacts(payload):
        return {day["date"]: day["impact_count"] for day in payload["days"]}

    during = _impacts((await c.get("/journal/days")).json())
    assert during[today.date().isoformat()] == 0
    # Only TODAY is withheld — a finished day is history and reports normally.
    assert during[yesterday.date().isoformat()] == 1

    alert.ended_at = today + timedelta(minutes=30)
    alert.closed_reason = "official"
    await s.commit()

    after = _impacts((await c.get("/journal/days")).json())
    assert after[today.date().isoformat()] == 1

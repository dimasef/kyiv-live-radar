"""Admin manual controls (/admin/*): cancel/restore a false-positive
threat/incident/alert, retype a track, and fix/remove a sighting — the parser
override tools. Verifies the write happened AND that a dismissed entity drops
out of the live views (/threats/active, /incidents/active, journal)."""
from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.security import encode_access
from app.config import settings
from app.db import Base, get_session
from app.main import app
from app.models import Alert, District, Incident, Threat, ThreatEvent, User


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "auth_jwt_secret", "admin-actions-secret")
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


async def _admin_headers(session) -> dict:
    user = User(email="admin@x.com", role="admin", password_hash="x")
    session.add(user)
    await session.commit()
    return {"Authorization": f"Bearer {encode_access(user)}"}


async def _district(session) -> District:
    d = District(name_uk="Тест", name_en="Test", lat=50.45, lon=30.52)
    session.add(d)
    await session.commit()
    return d


async def _threat_with_event(session, district, *, target_type="shahed", incident=None):
    threat = Threat(target_type=target_type, status="tracking")
    if incident is not None:
        threat.incident_id = incident.id
    session.add(threat)
    await session.commit()
    ev = ThreatEvent(threat_id=threat.id, district_id=district.id, raw_text="x")
    session.add(ev)
    await session.commit()
    return threat, ev


async def _active_ids(c, headers) -> set[int]:
    r = await c.get("/threats/active")
    assert r.status_code == 200
    return {t["id"] for t in r.json()}


async def test_dismiss_and_restore_threat(client):
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    threat, _ = await _threat_with_event(s, d)

    assert threat.id in await _active_ids(c, headers)

    r = await c.post(f"/admin/threats/{threat.id}/dismiss", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "dismissed"
    assert threat.id not in await _active_ids(c, headers)

    r = await c.post(f"/admin/threats/{threat.id}/restore", headers=headers)
    assert r.status_code == 200
    assert threat.id in await _active_ids(c, headers)


async def test_dismiss_excludes_threat_from_journal(client):
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    threat, _ = await _threat_with_event(s, d)

    def total_tracks(payload):
        return sum(day["track_count"] for day in payload["days"])

    before = (await c.get("/journal/days")).json()
    assert total_tracks(before) == 1

    await c.post(f"/admin/threats/{threat.id}/dismiss", headers=headers)
    after = (await c.get("/journal/days")).json()
    assert total_tracks(after) == 0


async def test_retype_updates_incident(client):
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    inc = Incident(target_type="shahed", attack_types=["shahed"])
    s.add(inc)
    await s.commit()
    threat, _ = await _threat_with_event(s, d, target_type="shahed", incident=inc)

    r = await c.patch(
        f"/admin/threats/{threat.id}", json={"target_type": "ballistic"}, headers=headers
    )
    assert r.status_code == 200
    assert r.json()["target_type"] == "ballistic"

    refreshed = await s.get(Incident, inc.id)
    await s.refresh(refreshed)
    assert refreshed.target_type == "ballistic"
    assert refreshed.attack_types == ["ballistic"]


async def test_retype_rejects_unknown_type(client):
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    threat, _ = await _threat_with_event(s, d)
    r = await c.patch(
        f"/admin/threats/{threat.id}", json={"target_type": "nonsense"}, headers=headers
    )
    assert r.status_code == 422


async def test_dismiss_incident_cancels_member_tracks(client):
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    inc = Incident(target_type="shahed", attack_types=["shahed"])
    s.add(inc)
    await s.commit()
    threat, _ = await _threat_with_event(s, d, incident=inc)

    r = await c.post(f"/admin/incidents/{inc.id}/dismiss", headers=headers)
    assert r.status_code == 200

    # Incident gone from active, member track cancelled + off the map.
    active_inc = (await c.get("/incidents/active")).json()
    assert inc.id not in {i["id"] for i in active_inc}
    assert threat.id not in await _active_ids(c, headers)
    refreshed = await s.get(Threat, threat.id)
    await s.refresh(refreshed)
    assert refreshed.closed_reason == "dismissed"

    # Restore brings both back.
    r = await c.post(f"/admin/incidents/{inc.id}/restore", headers=headers)
    assert r.status_code == 200
    assert threat.id in await _active_ids(c, headers)


async def test_delete_last_event_dismisses_track(client):
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    threat, ev = await _threat_with_event(s, d)

    r = await c.delete(f"/admin/events/{ev.id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "dismissed"
    assert threat.id not in await _active_ids(c, headers)


async def test_delete_one_of_two_events_keeps_track(client):
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    threat, ev1 = await _threat_with_event(s, d)
    ev2 = ThreatEvent(threat_id=threat.id, district_id=d.id, raw_text="y")
    s.add(ev2)
    await s.commit()

    r = await c.delete(f"/admin/events/{ev1.id}", headers=headers)
    assert r.status_code == 200
    assert threat.id in await _active_ids(c, headers)
    remaining = list(await s.scalars(select(ThreatEvent).where(ThreatEvent.threat_id == threat.id)))
    assert [e.id for e in remaining] == [ev2.id]


async def test_move_event_changes_district(client):
    c, s = client
    headers = await _admin_headers(s)
    d1 = await _district(s)
    d2 = District(name_uk="Друга", name_en="Second", lat=50.5, lon=30.6)
    s.add(d2)
    await s.commit()
    threat, ev = await _threat_with_event(s, d1)

    r = await c.patch(f"/admin/events/{ev.id}", json={"district_id": d2.id}, headers=headers)
    assert r.status_code == 200
    refreshed = await s.get(ThreatEvent, ev.id)
    await s.refresh(refreshed)
    assert refreshed.district_id == d2.id


async def test_move_event_rejects_unknown_district(client):
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    _, ev = await _threat_with_event(s, d)
    r = await c.patch(f"/admin/events/{ev.id}", json={"district_id": 99999}, headers=headers)
    assert r.status_code == 400


async def test_dismiss_and_restore_alert(client):
    c, s = client
    headers = await _admin_headers(s)
    alert = Alert(scope="city")
    s.add(alert)
    await s.commit()

    assert alert.id in {a["id"] for a in (await c.get("/alerts/active")).json()}

    r = await c.post(f"/admin/alerts/{alert.id}/dismiss", headers=headers)
    assert r.status_code == 200
    assert alert.id not in {a["id"] for a in (await c.get("/alerts/active")).json()}

    r = await c.post(f"/admin/alerts/{alert.id}/restore", headers=headers)
    assert r.status_code == 200
    assert alert.id in {a["id"] for a in (await c.get("/alerts/active")).json()}


async def test_dismissed_list(client):
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    threat, _ = await _threat_with_event(s, d)
    await c.post(f"/admin/threats/{threat.id}/dismiss", headers=headers)

    r = await c.get("/admin/dismissed", headers=headers)
    assert r.status_code == 200
    assert threat.id in {t["id"] for t in r.json()["threats"]}


async def test_admin_actions_require_admin(client):
    c, s = client
    d = await _district(s)
    threat, _ = await _threat_with_event(s, d)

    # Anonymous → 401.
    r = await c.post(f"/admin/threats/{threat.id}/dismiss")
    assert r.status_code == 401

    # Regular user → 403.
    user = User(email="u@x.com", role="user", password_hash="x")
    s.add(user)
    await s.commit()
    r = await c.post(
        f"/admin/threats/{threat.id}/dismiss",
        headers={"Authorization": f"Bearer {encode_access(user)}"},
    )
    assert r.status_code == 403

"""Admin sources/channels management endpoints (/admin/sources*).

Covers the CRUD + soft-deactivate + reactivate-on-readd behavior and the admin
gate. The listener-reload signal is patched to just record that it fired (there's
no real Telethon listener in tests)."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# The listener-reload hook is patched where it is USED, not where it is defined
# (`feeds.telegram`) — this is the module whose namespace holds the imported name.
import app.api.admin.sources as sources_routes
from app.auth.security import encode_access
from app.config import settings
from app.db import Base, get_session
from app.main import app
from app.models import (
    District,
    Incident,
    Notice,
    RawMessage,
    Source,
    Threat,
    ThreatEvent,
    User,
)


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "auth_jwt_secret", "sources-secret")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'t.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    reloads = {"count": 0}
    monkeypatch.setattr(sources_routes, "request_listener_reload", lambda: reloads.__setitem__("count", reloads["count"] + 1))

    async def _override():
        async with Session() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, Session, reloads
    app.dependency_overrides.clear()
    await engine.dispose()


async def _admin_headers(Session, role: str = "admin") -> dict:
    async with Session() as s:
        user = User(email=f"{role}@x.com", role=role, password_hash="x")
        s.add(user)
        await s.commit()
        return {"Authorization": f"Bearer {encode_access(user)}"}


async def test_add_source_creates_active_row_and_reloads(client):
    c, Session, reloads = client
    headers = await _admin_headers(Session)

    r = await c.post("/admin/sources", json={"subscribe_ref": "@NightWatch", "role": "spotter"}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["channel_key"] == "NightWatch"  # @ stripped
    assert body["subscribe_ref"] == "NightWatch"
    assert body["is_active"] is True
    assert body["stats"]["messages_total"] == 0
    assert reloads["count"] == 1


async def test_deactivate_is_soft_and_reactivate_via_readd(client):
    c, Session, reloads = client
    headers = await _admin_headers(Session)

    add = await c.post("/admin/sources", json={"subscribe_ref": "chanX"}, headers=headers)
    sid = add.json()["id"]

    off = await c.post(f"/admin/sources/{sid}/deactivate", headers=headers)
    assert off.status_code == 200 and off.json()["is_active"] is False

    # The row is soft-deleted — still present.
    async with Session() as s:
        assert await s.scalar(select(func.count()).select_from(Source)) == 1

    # Re-adding the same handle reactivates the SAME row (no duplicate key).
    again = await c.post("/admin/sources", json={"subscribe_ref": "chanX"}, headers=headers)
    assert again.status_code == 200
    assert again.json()["id"] == sid and again.json()["is_active"] is True
    async with Session() as s:
        assert await s.scalar(select(func.count()).select_from(Source)) == 1


async def test_patch_role_reloads_but_weight_does_not(client):
    c, Session, reloads = client
    headers = await _admin_headers(Session)
    sid = (await c.post("/admin/sources", json={"subscribe_ref": "c"}, headers=headers)).json()["id"]
    reloads["count"] = 0

    # trust_weight is inert w.r.t. subscription -> no reload.
    w = await c.patch(f"/admin/sources/{sid}", json={"trust_weight": 0.3}, headers=headers)
    assert w.json()["trust_weight"] == 0.3
    assert reloads["count"] == 0

    # Same for the type-inheritance window — it steers messages already arriving.
    assert (await c.get("/admin/sources", headers=headers)).json()[0][
        "type_inherit_minutes"
    ] is None
    win = await c.patch(
        f"/admin/sources/{sid}", json={"type_inherit_minutes": 30}, headers=headers
    )
    assert win.json()["type_inherit_minutes"] == 30
    assert reloads["count"] == 0
    # Bounded: a typo would otherwise type a whole night off one stale mention.
    bad = await c.patch(
        f"/admin/sources/{sid}", json={"type_inherit_minutes": 300}, headers=headers
    )
    assert bad.status_code == 422

    # role change affects routing -> reload.
    role = await c.patch(f"/admin/sources/{sid}", json={"role": "alert"}, headers=headers)
    assert role.json()["role"] == "alert"
    assert reloads["count"] == 1


async def test_delete_wipes_channel_data_and_empty_track(client):
    c, Session, _ = client
    headers = await _admin_headers(Session)
    # A channel with a raw message, a notice, and a single-source track+incident.
    async with Session() as s:
        d = District(name_uk="Троєщина", name_en="Troieshchyna", lat=50.5, lon=30.6)
        src = Source(channel_key="doomed", name="Doomed")
        s.add_all([d, src])
        await s.commit()
        sid = src.id
        # Closed incident — deleting a source is guarded against MID-attack, so
        # this must not look like a live attack.
        inc = Incident(target_type="shahed", ended_at=datetime(2026, 7, 1, tzinfo=UTC))
        s.add(inc)
        await s.commit()
        t = Threat(target_type="shahed", status="tracking", incident_id=inc.id)
        s.add(t)
        await s.commit()
        s.add_all([
            RawMessage(source_id=sid, message_id=1, text="Шахед Троєщина", processed=True),
            Notice(source_id=sid, kind="status", text="x"),
            ThreatEvent(threat_id=t.id, district_id=d.id, source_id=sid, decision_source="rule"),
        ])
        await s.commit()

    r = await c.delete(f"/admin/sources/{sid}", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["raw_messages"] == 1 and body["events"] == 1 and body["notices"] == 1
    assert body["threats_deleted"] == 1 and body["incidents_deleted"] == 1

    # Everything is gone: source, its raw/notice/event, and the now-empty track+incident.
    async with Session() as s:
        assert await s.scalar(select(func.count()).select_from(Source)) == 0
        assert await s.scalar(select(func.count()).select_from(RawMessage)) == 0
        assert await s.scalar(select(func.count()).select_from(Notice)) == 0
        assert await s.scalar(select(func.count()).select_from(ThreatEvent)) == 0
        assert await s.scalar(select(func.count()).select_from(Threat)) == 0
        assert await s.scalar(select(func.count()).select_from(Incident)) == 0


async def test_delete_keeps_track_shared_with_another_source(client):
    """A track fed by two channels survives deleting one — it keeps the other's
    events (only the deleted source's contribution is removed)."""
    c, Session, _ = client
    headers = await _admin_headers(Session)
    async with Session() as s:
        d = District(name_uk="Троєщина", name_en="Troieshchyna", lat=50.5, lon=30.6)
        a = Source(channel_key="a", name="A")
        b = Source(channel_key="b", name="B")
        s.add_all([d, a, b])
        await s.commit()
        aid, bid = a.id, b.id
        t = Threat(target_type="shahed", status="tracking")
        s.add(t)
        await s.commit()
        s.add_all([
            ThreatEvent(threat_id=t.id, district_id=d.id, source_id=aid, decision_source="rule"),
            ThreatEvent(threat_id=t.id, district_id=d.id, source_id=bid, decision_source="rule"),
        ])
        await s.commit()
        tid = t.id

    r = await c.delete(f"/admin/sources/{aid}", headers=headers)
    assert r.status_code == 200
    assert r.json()["threats_deleted"] == 0  # track survives on B's event

    async with Session() as s:
        assert await s.scalar(select(func.count()).select_from(Threat)) == 1
        remaining = await s.scalars(select(ThreatEvent).where(ThreatEvent.threat_id == tid))
        rows = list(remaining)
        assert len(rows) == 1 and rows[0].source_id == bid


async def test_requires_admin(client):
    c, Session, _ = client
    assert (await c.get("/admin/sources")).status_code == 401

    user_headers = await _admin_headers(Session, role="user")
    assert (await c.get("/admin/sources", headers=user_headers)).status_code == 403

"""Admin-triggered reprocess endpoints (/admin/reprocess/*).

Tests the ENDPOINT orchestration — pre-flight scope, the mid-attack guard, and
the before/after diff — with `run_reprocess` STUBBED. The real reprocess (wipe +
replay) is covered by test_reprocess.py and exercised in prod/CLI; here we must
not invoke it (it touches global migrate/seed and would hit the dev DB)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.pipeline.reprocess as reprocess
from app.auth.security import encode_access
from app.config import settings
from app.db import Base, get_session
from app.main import app
from app.models import District, Incident, RawMessage, Source, Threat, ThreatEvent, User


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "auth_jwt_secret", "reproc-secret")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'t.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    # The endpoints read/rebuild via reprocess.SessionLocal — wire it to the test DB.
    monkeypatch.setattr(reprocess, "SessionLocal", Session)

    # A stub reprocess: simulate a wipe (drop all threats) so the before/after
    # diff has something to show, without running the real global-touching one.
    async def fake_run_reprocess(no_llm: bool = True):
        async with Session() as s:
            await s.execute(delete(ThreatEvent))
            await s.execute(delete(Threat))
            await s.commit()
        return {"messages": 5, "matched": 3, "tracks": 0, "events": 0}

    monkeypatch.setattr(reprocess, "run_reprocess", fake_run_reprocess)

    async def _override():
        async with Session() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, Session
    app.dependency_overrides.clear()
    await engine.dispose()


async def _admin_headers(Session) -> dict:
    async with Session() as s:
        user = User(email="admin@x.com", role="admin", password_hash="x")
        s.add(user)
        await s.commit()
        return {"Authorization": f"Bearer {encode_access(user)}"}


async def _seed_activity(Session, *, open_incident: bool = False) -> None:
    """One raw message + one track. The incident is left OPEN (ended_at NULL) to
    exercise the mid-attack guard, or CLOSED so a reprocess is allowed."""
    async with Session() as s:
        d = District(name_uk="Троєщина", name_en="Troieshchyna", lat=50.5, lon=30.6)
        src = Source(channel_key="s", name="S")
        s.add_all([d, src])
        await s.commit()
        s.add(RawMessage(source_id=src.id, message_id=1, text="Шахед курс на Троєщину"))
        inc = Incident(
            target_type="shahed",
            ended_at=None if open_incident else datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        s.add(inc)
        await s.commit()
        t = Threat(target_type="shahed", status="tracking", incident_id=inc.id)
        s.add(t)
        await s.commit()
        s.add(ThreatEvent(threat_id=t.id, district_id=d.id, raw_text="x"))
        await s.commit()


async def test_preview_reports_scope(client):
    c, Session = client
    headers = await _admin_headers(Session)
    await _seed_activity(Session)

    r = await c.get("/admin/reprocess/preview", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["raw_messages"] == 1
    assert body["current"]["tracks"] == 1
    assert body["attack_active"] is False


async def test_apply_returns_before_after_diff(client):
    c, Session = client
    headers = await _admin_headers(Session)
    await _seed_activity(Session)

    r = await c.post("/admin/reprocess/apply", json={}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["before"]["tracks"] == 1
    assert body["after"]["tracks"] == 0  # the stub wiped them
    assert body["result"]["messages"] == 5


async def test_apply_refuses_mid_attack(client):
    c, Session = client
    headers = await _admin_headers(Session)
    await _seed_activity(Session, open_incident=True)

    r = await c.post("/admin/reprocess/apply", json={}, headers=headers)
    assert r.status_code == 409

    # force overrides the guard.
    r = await c.post("/admin/reprocess/apply", json={"force": True}, headers=headers)
    assert r.status_code == 200


async def test_reprocess_requires_admin(client):
    c, Session = client
    r = await c.get("/admin/reprocess/preview")
    assert r.status_code == 401

    async with Session() as s:
        user = User(email="u@x.com", role="user", password_hash="x")
        s.add(user)
        await s.commit()
        tok = encode_access(user)
    r = await c.get("/admin/reprocess/preview", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403

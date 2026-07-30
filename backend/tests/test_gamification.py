"""Gamification card-analysis API (app/api/gamification.py), driven over
ASGITransport — mirrors tests/test_friends.py. The shared test session is also
handed to each test so it can insert Threat rows to analyse."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import random

from app.config import settings
from app.db import Base, get_session
from app.domain.cards import CARD_COUNT, CARD_RARITY, draw_card
from app.main import app
from app.models import Threat


def test_draw_card_is_weighted_by_rarity():
    """Every draw is a valid id, and over many draws commons clearly outnumber
    legendaries (weights 6:3:1) — the rarity actually biases the drop."""
    random.seed(1)
    draws = [draw_card() for _ in range(6000)]
    assert all(1 <= c <= CARD_COUNT for c in draws)
    commons = sum(1 for c in draws if CARD_RARITY[c] == "common")
    legendaries = sum(1 for c in draws if CARD_RARITY[c] == "legendary")
    assert commons > legendaries * 2  # huge margin — not flaky


@pytest_asyncio.fixture
async def env(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "auth_jwt_secret", "api-test-secret")
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


async def _register(c: AsyncClient, email: str) -> dict:
    r = await c.post("/auth/register", json={"email": email, "password": "password123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access']}"}


async def _new_threat(s, *, target_type="shahed", status="tracking", scope="district", created_at=None) -> int:
    t = Threat(target_type=target_type, status=status, scope=scope, kind="track")
    if created_at is not None:
        t.created_at = created_at
    s.add(t)
    await s.commit()
    return t.id


async def test_track_analysis_awards_card_and_shows_in_collection(env):
    c, s = env
    auth = await _register(c, "a@x.com")
    tid = await _new_threat(s)

    r = await c.post("/analysis", json={"threat_id": tid, "kind": "track"}, headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "track"
    assert 1 <= body["card_id"] <= CARD_COUNT

    r = await c.get("/analysis/collection", headers=auth)
    assert r.status_code == 200
    col = r.json()
    assert col["total_analyses"] == 1
    assert col["card_count"] == CARD_COUNT
    assert len(col["cards"]) == 1 and col["cards"][0]["count"] == 1


async def test_remains_requires_destroyed(env):
    c, s = env
    auth = await _register(c, "a@x.com")
    tid = await _new_threat(s, status="tracking")

    # Debris analysis is not offered while the target is still flying.
    r = await c.post("/analysis", json={"threat_id": tid, "kind": "remains"}, headers=auth)
    assert r.status_code == 409

    # Once destroyed: remains works, and the live 'track' analysis no longer does.
    t = await s.get(Threat, tid)
    t.status = "destroyed"
    await s.commit()

    r = await c.post("/analysis", json={"threat_id": tid, "kind": "remains"}, headers=auth)
    assert r.status_code == 200, r.text
    r = await c.post("/analysis", json={"threat_id": tid, "kind": "track"}, headers=auth)
    assert r.status_code == 409


async def test_same_kind_claimed_once_globally(env):
    c, s = env
    a = await _register(c, "a@x.com")
    b = await _register(c, "b@x.com")
    tid = await _new_threat(s)

    r = await c.post("/analysis", json={"threat_id": tid, "kind": "track"}, headers=a)
    assert r.status_code == 200
    # Second user loses the race for the same threat+kind.
    r = await c.post("/analysis", json={"threat_id": tid, "kind": "track"}, headers=b)
    assert r.status_code == 409

    # B's collection stays empty — a lost race awards nothing.
    r = await c.get("/analysis/collection", headers=b)
    assert r.json()["total_analyses"] == 0


async def test_state_reflects_claims(env):
    c, s = env
    a = await _register(c, "a@x.com")
    b = await _register(c, "b@x.com")
    tid = await _new_threat(s)
    await c.post("/analysis", json={"threat_id": tid, "kind": "track"}, headers=a)

    r = await c.get(f"/analysis/threat/{tid}", headers=a)
    st = r.json()
    assert st["track_taken"] is True and st["remains_taken"] is False
    assert st["mine_track"] is not None  # A sees the card it won

    r = await c.get(f"/analysis/threat/{tid}", headers=b)
    st = r.json()
    assert st["track_taken"] is True and st["mine_track"] is None  # taken, but not by B


@pytest.mark.parametrize("status", ["lost", "impact", "destroyed"])
async def test_off_board_statuses_allow_remains(env, status):
    c, s = env
    auth = await _register(c, "a@x.com")
    tid = await _new_threat(s, status=status)
    r = await c.post("/analysis", json={"threat_id": tid, "kind": "remains"}, headers=auth)
    assert r.status_code == 200, r.text
    # ...and 'track' is not offered for an off-board target.
    r = await c.post("/analysis", json={"threat_id": tid, "kind": "track"}, headers=auth)
    assert r.status_code == 409


async def test_unknown_type_not_eligible(env):
    c, s = env
    auth = await _register(c, "a@x.com")
    tid = await _new_threat(s, target_type="unknown")
    r = await c.post("/analysis", json={"threat_id": tid, "kind": "track"}, headers=auth)
    assert r.status_code == 409


async def test_city_scope_not_eligible(env):
    c, s = env
    auth = await _register(c, "a@x.com")
    tid = await _new_threat(s, scope="city")
    r = await c.post("/analysis", json={"threat_id": tid, "kind": "track"}, headers=auth)
    assert r.status_code == 409


async def test_stale_target_blocked(env):
    from datetime import datetime, timedelta, timezone

    c, s = env
    auth = await _register(c, "a@x.com")
    old = datetime.now(timezone.utc) - timedelta(hours=13)
    tid = await _new_threat(s, created_at=old)
    r = await c.post("/analysis", json={"threat_id": tid, "kind": "track"}, headers=auth)
    assert r.status_code == 409


async def test_gamification_pref_persists_and_syncs(env):
    c, s = env
    auth = await _register(c, "a@x.com")
    # Default off.
    r = await c.get("/auth/me", headers=auth)
    assert r.json()["gamification"] is False
    # Enable → persisted → visible to any other session (e.g. another device).
    r = await c.put("/me/gamification", json={"enabled": True}, headers=auth)
    assert r.status_code == 200 and r.json()["enabled"] is True
    r = await c.get("/auth/me", headers=auth)
    assert r.json()["gamification"] is True


async def test_friend_collection_gated(env):
    c, s = env
    a = await _register(c, "a@x.com")
    b = await _register(c, "b@x.com")
    # ids: a=1, b=2 (fresh DB, registration order).
    # Not friends → B can't see A's collection.
    r = await c.get("/collection/1", headers=b)
    assert r.status_code == 403
    # Your own via the id route always works.
    r = await c.get("/collection/2", headers=b)
    assert r.status_code == 200
    # Become friends (A requests, B accepts) → B can now see A's collection.
    await c.post("/friends/requests", json={"email": "b@x.com"}, headers=a)
    reqs = (await c.get("/friends/requests", headers=b)).json()["incoming"]
    await c.post(f"/friends/requests/{reqs[0]['id']}/accept", headers=b)
    r = await c.get("/collection/1", headers=b)
    assert r.status_code == 200 and "cards" in r.json()


async def test_requires_auth(env):
    c, s = env
    tid = await _new_threat(s)
    r = await c.post("/analysis", json={"threat_id": tid, "kind": "track"})
    assert r.status_code == 401


async def test_bad_kind_rejected(env):
    c, s = env
    auth = await _register(c, "a@x.com")
    tid = await _new_threat(s)
    r = await c.post("/analysis", json={"threat_id": tid, "kind": "nope"}, headers=auth)
    assert r.status_code == 400

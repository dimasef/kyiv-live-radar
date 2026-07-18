"""Push subscribe/unsubscribe/config routes (app/api/routes.py).

First API-level test file: drives the real FastAPI app over httpx's
ASGITransport (no server, no lifespan) with get_session overridden onto a temp
SQLite DB.
"""

from datetime import datetime, timezone

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db import Base, get_session
from app.main import app
from app.models import District, PushSubscription

SQUARE = {
    "type": "Polygon",
    "coordinates": [[[30.4, 50.4], [30.6, 50.4], [30.6, 50.6], [30.4, 50.6], [30.4, 50.4]]],
}

SUB = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "k", "auth": "a"}}


@pytest_asyncio.fixture
async def ctx(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'t.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        s.add(District(name_uk="Квадратний", name_en="Square", lat=50.5, lon=30.5,
                       aliases=[], boundary=SQUARE))
        await s.commit()

        async def _override():
            yield s

        app.dependency_overrides[get_session] = _override
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, s
        app.dependency_overrides.clear()
    await engine.dispose()


async def test_subscribe_creates_row_and_resolves_raion(ctx):
    client, s = ctx
    r = await client.post("/push/subscribe", json={
        "subscription": SUB,
        "home": {"lat": 50.5, "lon": 30.5, "radius_km": 4.0},
    })
    assert r.status_code == 200 and r.json() == {"ok": True}
    sub = (await s.scalars(select(PushSubscription))).one()
    square_id = (await s.scalars(select(District.id))).one()
    assert (sub.home_lat, sub.home_lon, sub.home_radius_km) == (50.5, 30.5, 4.0)
    assert sub.home_district_id == square_id


async def test_repost_updates_home_and_resets_danger_state(ctx):
    client, s = ctx
    await client.post("/push/subscribe", json={
        "subscription": SUB, "home": {"lat": 50.5, "lon": 30.5, "radius_km": 3.0},
    })
    sub = (await s.scalars(select(PushSubscription))).one()
    sub.danger_state = {"7": {"level": 1, "max_pushed": 1, "pushed_at": None}}
    await s.commit()

    # moved home outside the raion square -> raion cleared, state reset
    r = await client.post("/push/subscribe", json={
        "subscription": SUB, "home": {"lat": 49.0, "lon": 29.0, "radius_km": 5.0},
    })
    assert r.status_code == 200
    await s.refresh(sub)
    assert (sub.home_lat, sub.home_lon, sub.home_radius_km) == (49.0, 29.0, 5.0)
    assert sub.home_district_id is None
    assert sub.danger_state == {}
    # still exactly one row — upsert by endpoint, not insert
    assert len(list(await s.scalars(select(PushSubscription)))) == 1


async def test_radius_only_change_keeps_danger_state(ctx):
    client, s = ctx
    await client.post("/push/subscribe", json={
        "subscription": SUB, "home": {"lat": 50.5, "lon": 30.5, "radius_km": 3.0},
    })
    sub = (await s.scalars(select(PushSubscription))).one()
    sub.danger_state = {"7": {"level": 1, "max_pushed": 1, "pushed_at": None}}
    await s.commit()

    await client.post("/push/subscribe", json={
        "subscription": SUB, "home": {"lat": 50.5, "lon": 30.5, "radius_km": 8.0},
    })
    await s.refresh(sub)
    assert sub.home_radius_km == 8.0
    assert sub.danger_state != {}


async def test_unsubscribe_is_idempotent(ctx):
    client, s = ctx
    await client.post("/push/subscribe", json={"subscription": SUB})
    r = await client.request("DELETE", "/push/subscribe", json={"endpoint": SUB["endpoint"]})
    assert r.status_code == 200
    assert list(await s.scalars(select(PushSubscription))) == []
    # deleting again is a no-op success
    r = await client.request("DELETE", "/push/subscribe", json={"endpoint": SUB["endpoint"]})
    assert r.status_code == 200


async def test_push_config_reflects_vapid_keys(ctx, monkeypatch):
    client, _ = ctx
    monkeypatch.setattr(settings, "vapid_public_key", "")
    monkeypatch.setattr(settings, "vapid_private_key", "")
    r = await client.get("/push/config")
    assert r.json() == {"enabled": False, "public_key": None}

    monkeypatch.setattr(settings, "vapid_public_key", "pub")
    monkeypatch.setattr(settings, "vapid_private_key", "priv")
    r = await client.get("/push/config")
    assert r.json() == {"enabled": True, "public_key": "pub"}

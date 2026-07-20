"""Google sign-in route (app/api/auth_routes.py) with the id_token verification
monkeypatched — never hits Google."""
from __future__ import annotations

import app.api.auth_routes as auth_routes
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db import Base, get_session
from app.main import app
from app.models import OAuthIdentity


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "auth_jwt_secret", "google-test-secret")
    monkeypatch.setattr(settings, "google_client_id", "test-client-id")
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


def _patch_profile(monkeypatch, profile):
    async def _fake(credential, client_id):
        return profile

    monkeypatch.setattr(auth_routes, "verify_google_id_token", _fake)


async def test_google_creates_user_and_is_idempotent(client, monkeypatch):
    c, s = client
    _patch_profile(monkeypatch, {
        "sub": "g-1", "email": "person@gmail.com", "email_verified": True,
        "name": "Person", "picture": "http://pic",
    })
    r = await c.post("/auth/google", json={"credential": "tok"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["email"] == "person@gmail.com"
    assert "google" in body["user"]["providers"]
    uid = body["user"]["id"]

    # Second call → same user, still exactly one identity row.
    r = await c.post("/auth/google", json={"credential": "tok"})
    assert r.json()["user"]["id"] == uid
    count = await s.scalar(select(func.count()).select_from(OAuthIdentity))
    assert count == 1


async def test_google_links_to_existing_email_account(client, monkeypatch):
    c, _ = client
    # Pre-existing password account with the same email.
    r = await c.post("/auth/register", json={"email": "dup@gmail.com", "password": "password123"})
    uid = r.json()["user"]["id"]

    _patch_profile(monkeypatch, {
        "sub": "g-2", "email": "dup@gmail.com", "email_verified": True,
        "name": "Dup", "picture": None,
    })
    r = await c.post("/auth/google", json={"credential": "tok"})
    assert r.status_code == 200
    assert r.json()["user"]["id"] == uid  # merged, not a new account
    assert set(r.json()["user"]["providers"]) == {"password", "google"}


async def test_google_unverified_email_rejected(client, monkeypatch):
    c, _ = client
    _patch_profile(monkeypatch, {
        "sub": "g-3", "email": "x@gmail.com", "email_verified": False,
        "name": "X", "picture": None,
    })
    r = await c.post("/auth/google", json={"credential": "tok"})
    assert r.status_code == 401

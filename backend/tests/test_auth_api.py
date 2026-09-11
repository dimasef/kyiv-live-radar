"""Auth API happy paths (app/api/auth_routes.py), driven over ASGITransport —
mirrors tests/test_push_api.py."""
from __future__ import annotations

from app.config import settings


async def test_register_login_me_flow(client, session):
    c, _ = client, session
    r = await c.post("/auth/register", json={"email": "A@B.com", "password": "password123"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["email"] == "a@b.com"  # normalized lowercase
    assert body["user"]["role"] == "user"
    assert body["user"]["providers"] == ["password"]
    assert body["access"] and body["refresh"]

    # Duplicate registration is rejected.
    r = await c.post("/auth/register", json={"email": "a@b.com", "password": "password123"})
    assert r.status_code == 400

    # Login (case-insensitive email).
    r = await c.post("/auth/login", json={"email": "a@b.com", "password": "password123"})
    assert r.status_code == 200
    access = r.json()["access"]

    # Wrong password → 401.
    r = await c.post("/auth/login", json={"email": "a@b.com", "password": "nope-nope-nope"})
    assert r.status_code == 401

    # Unknown email → same 401 (no enumeration).
    r = await c.post("/auth/login", json={"email": "ghost@b.com", "password": "password123"})
    assert r.status_code == 401

    # /auth/me with the bearer token.
    r = await c.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200 and r.json()["email"] == "a@b.com"

    # /auth/me without a token → 401.
    r = await c.get("/auth/me")
    assert r.status_code == 401


async def test_refresh_issues_new_access(client, session):
    c, _ = client, session
    r = await c.post("/auth/register", json={"email": "x@y.com", "password": "password123"})
    tokens = r.json()
    r = await c.post("/auth/refresh", json={"refresh": tokens["refresh"]})
    assert r.status_code == 200
    new_access = r.json()["access"]
    r = await c.get("/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    assert r.status_code == 200 and r.json()["email"] == "x@y.com"

    # An access token cannot be used where a refresh token is expected.
    r = await c.post("/auth/refresh", json={"refresh": tokens["access"]})
    assert r.status_code == 401


async def test_short_password_rejected(client, session):
    c, _ = client, session
    r = await c.post("/auth/register", json={"email": "s@t.com", "password": "short"})
    assert r.status_code == 422  # pydantic min_length


async def test_unconfigured_auth_returns_503(client, session, monkeypatch):
    c, _ = client, session
    monkeypatch.setattr(settings, "auth_jwt_secret", "")
    monkeypatch.setattr(settings, "environment", "production")
    r = await c.post("/auth/register", json={"email": "z@z.com", "password": "password123"})
    assert r.status_code == 503

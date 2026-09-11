"""Google sign-in route (app/api/auth_routes.py) with the id_token verification
monkeypatched — never hits Google."""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

import app.api.auth_routes as auth_routes
from app.config import settings
from app.models import OAuthIdentity


@pytest.fixture(autouse=True)
def _google_client_id(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "test-client-id")


def _patch_profile(monkeypatch, profile):
    async def _fake(credential, client_id):
        return profile

    monkeypatch.setattr(auth_routes, "verify_google_id_token", _fake)


async def test_google_creates_user_and_is_idempotent(client, session, monkeypatch):
    c, s = client, session
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


async def test_google_links_to_existing_email_account(client, session, monkeypatch):
    c, _ = client, session
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


async def test_google_unverified_email_rejected(client, session, monkeypatch):
    c, _ = client, session
    _patch_profile(monkeypatch, {
        "sub": "g-3", "email": "x@gmail.com", "email_verified": False,
        "name": "X", "picture": None,
    })
    r = await c.post("/auth/google", json={"credential": "tok"})
    assert r.status_code == 401

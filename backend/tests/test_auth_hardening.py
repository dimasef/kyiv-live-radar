"""Refresh-token rotation/revocation and the auth rate limits."""
from __future__ import annotations

from sqlalchemy import func, select

from app.config import settings
from app.models import RefreshToken

CREDS = {"email": "rot@example.com", "password": "password123"}


async def _register(client):
    r = await client.post("/auth/register", json=CREDS)
    assert r.status_code == 200, r.text
    return r.json()


async def test_refresh_rotates_and_old_token_dies(client, session):
    pair = await _register(client)
    r = await client.post("/auth/refresh", json={"refresh": pair["refresh"]})
    assert r.status_code == 200
    fresh = r.json()
    assert fresh["refresh"] != pair["refresh"]
    # The consumed token is gone.
    r = await client.post("/auth/refresh", json={"refresh": pair["refresh"]})
    assert r.status_code == 401
    # ...and its reuse revoked the family, including the replacement.
    r = await client.post("/auth/refresh", json={"refresh": fresh["refresh"]})
    assert r.status_code == 401
    live = await session.scalar(
        select(func.count()).select_from(RefreshToken).where(RefreshToken.revoked_at.is_(None))
    )
    assert live == 0


async def test_logout_revokes_refresh(client):
    pair = await _register(client)
    r = await client.post("/auth/logout", json={"refresh": pair["refresh"]})
    assert r.status_code == 200
    r = await client.post("/auth/refresh", json={"refresh": pair["refresh"]})
    assert r.status_code == 401


async def test_logout_without_body_is_fine(client):
    assert (await client.post("/auth/logout")).status_code == 200


async def test_refresh_minted_before_rotation_is_refused(client, session):
    """A token whose jti has no row (issued before migration 0048) is invalid."""
    pair = await _register(client)
    await session.execute(RefreshToken.__table__.delete())
    await session.commit()
    r = await client.post("/auth/refresh", json={"refresh": pair["refresh"]})
    assert r.status_code == 401


async def test_blocked_user_refresh_refused(client, session):
    pair = await _register(client)
    from app.models import User

    user = await session.scalar(select(User).where(User.email == CREDS["email"]))
    user.is_active = False
    await session.commit()
    r = await client.post("/auth/refresh", json={"refresh": pair["refresh"]})
    assert r.status_code == 401


async def test_login_locks_email_after_failed_attempts(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_login_attempts_per_email", 3)
    monkeypatch.setattr(settings, "auth_rate_limit_per_minute", 100)
    await _register(client)
    bad = {"email": CREDS["email"], "password": "wrong-password"}
    for _ in range(3):
        assert (await client.post("/auth/login", json=bad)).status_code == 401
    r = await client.post("/auth/login", json=bad)
    assert r.status_code == 429
    assert "Retry-After" in r.headers
    # The right password is refused too while the lock holds — that is the point.
    assert (await client.post("/auth/login", json=CREDS)).status_code == 429


async def test_login_success_clears_failed_counter(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_login_attempts_per_email", 3)
    await _register(client)
    bad = {"email": CREDS["email"], "password": "wrong-password"}
    for _ in range(2):
        await client.post("/auth/login", json=bad)
    assert (await client.post("/auth/login", json=CREDS)).status_code == 200
    for _ in range(2):
        await client.post("/auth/login", json=bad)
    assert (await client.post("/auth/login", json=bad)).status_code == 401


async def test_per_ip_limit_on_register(client):
    from app.api.ratelimit import limiter

    for _ in range(20):
        limiter.hit("auth:127.0.0.1", 20, 60)
    r = await client.post("/auth/register", json={"email": "x@example.com", "password": "password123"})
    assert r.status_code == 429


async def test_push_endpoint_must_be_a_push_service(client):
    body = {"subscription": {"endpoint": "https://10.0.0.1/admin", "keys": {"p256dh": "k", "auth": "a"}}}
    assert (await client.post("/push/subscribe", json=body)).status_code == 422
    body["subscription"]["endpoint"] = "http://fcm.googleapis.com/fcm/send/x"
    assert (await client.post("/push/subscribe", json=body)).status_code == 422
    body["subscription"]["endpoint"] = "https://web.push.apple.com/QAbc"
    assert (await client.post("/push/subscribe", json=body)).status_code == 200

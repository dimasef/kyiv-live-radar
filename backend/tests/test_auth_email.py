"""Email verification + password reset (app/auth/verification.py, auth routes).
Mail is captured by the `outbox` fixture; verification is switched ON here
(conftest turns it off for the rest of the suite)."""
from __future__ import annotations

import re

import pytest
from sqlalchemy import select

import app.api.public.auth_routes as auth_routes
from app.config import settings
from app.models import EmailToken, User

CREDS = {"email": "new@example.com", "password": "password123"}


@pytest.fixture(autouse=True)
def _verification_on(monkeypatch):
    monkeypatch.setattr(settings, "email_verification_enabled", True)
    monkeypatch.setattr(settings, "public_app_url", "https://radar.test")


def _token(text: str, path: str) -> str:
    m = re.search(rf"https://radar\.test{path}\?token=([A-Za-z0-9_\-%]+)", text)
    assert m, text
    return m.group(1)


async def test_register_sends_link_and_login_waits_for_it(client, outbox):
    r = await client.post("/auth/register", json=CREDS)
    assert r.status_code == 202, r.text
    assert r.json() == {"status": "verification_sent", "email": CREDS["email"]}
    assert "access" not in r.json()
    assert len(outbox) == 1 and outbox[0][0] == CREDS["email"]

    r = await client.post("/auth/login", json=CREDS)
    assert r.status_code == 403
    assert r.json()["detail"] == {"code": "email_unverified"}

    token = _token(outbox[0][2], "/verify-email")
    r = await client.post("/auth/verify-email", json={"token": token})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["email"] == CREDS["email"]
    assert "refresh" in r.json()

    # The link is single-use.
    r = await client.post("/auth/verify-email", json={"token": token})
    assert r.status_code == 400
    assert (await client.post("/auth/login", json=CREDS)).status_code == 200


async def test_verified_email_counts_for_admin_allowlist(client, outbox, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", CREDS["email"])
    await client.post("/auth/register", json=CREDS)
    r = await client.post("/auth/verify-email", json={"token": _token(outbox[0][2], "/verify-email")})
    assert r.json()["user"]["role"] == "admin"


async def test_resend_retires_the_earlier_link(client, outbox):
    await client.post("/auth/register", json=CREDS)
    first = _token(outbox[0][2], "/verify-email")
    r = await client.post("/auth/resend-verification", json={"email": CREDS["email"]})
    assert r.status_code == 200 and len(outbox) == 2
    second = _token(outbox[1][2], "/verify-email")
    assert (await client.post("/auth/verify-email", json={"token": first})).status_code == 400
    assert (await client.post("/auth/verify-email", json={"token": second})).status_code == 200


async def test_resend_and_forgot_never_reveal_accounts(client, outbox):
    r = await client.post("/auth/resend-verification", json={"email": "nobody@example.com"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    r = await client.post("/auth/forgot-password", json={"email": "nobody@example.com"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert outbox == []


async def test_mail_per_email_limit(client, outbox, monkeypatch):
    monkeypatch.setattr(settings, "auth_mail_per_email", 2)
    for _ in range(2):
        assert (await client.post("/auth/forgot-password", json={"email": CREDS["email"]})).status_code == 200
    assert (await client.post("/auth/forgot-password", json={"email": CREDS["email"]})).status_code == 429


async def test_password_reset_verifies_and_signs_out_other_sessions(client, session, outbox):
    await client.post("/auth/register", json=CREDS)
    await client.post("/auth/verify-email", json={"token": _token(outbox[0][2], "/verify-email")})
    pair = (await client.post("/auth/login", json=CREDS)).json()

    r = await client.post("/auth/forgot-password", json={"email": CREDS["email"]})
    assert r.status_code == 200
    token = _token(outbox[-1][2], "/reset-password")
    r = await client.post("/auth/reset-password", json={"token": token, "password": "brand-new-pass"})
    assert r.status_code == 200, r.text
    assert (await client.post("/auth/login", json=CREDS)).status_code == 401
    assert (
        await client.post("/auth/login", json={"email": CREDS["email"], "password": "brand-new-pass"})
    ).status_code == 200
    # The session from before the reset is gone.
    assert (await client.post("/auth/refresh", json={"refresh": pair["refresh"]})).status_code == 401
    # Reset tokens are not verification tokens.
    assert (await client.post("/auth/verify-email", json={"token": token})).status_code == 400


async def test_reset_reclaims_a_squatted_address(client, session, outbox):
    """Someone registered my email with their password and never verified.
    The reset link goes to ME, and using it makes the account mine."""
    await client.post("/auth/register", json={"email": CREDS["email"], "password": "squatter-pass"})
    await client.post("/auth/forgot-password", json={"email": CREDS["email"]})
    token = _token(outbox[-1][2], "/reset-password")
    r = await client.post("/auth/reset-password", json={"token": token, "password": "owner-pass-123"})
    assert r.status_code == 200
    user = await session.scalar(select(User).where(User.email == CREDS["email"]))
    assert user.email_verified is True
    assert (
        await client.post("/auth/login", json={"email": CREDS["email"], "password": "squatter-pass"})
    ).status_code == 401


async def test_expired_token_refused(client, session, outbox, monkeypatch):
    monkeypatch.setattr(settings, "auth_verify_ttl_hours", 0)
    await client.post("/auth/register", json=CREDS)
    token = _token(outbox[0][2], "/verify-email")
    assert (await client.post("/auth/verify-email", json={"token": token})).status_code == 400
    rows = list(await session.scalars(select(EmailToken)))
    assert len(rows) == 1 and rows[0].used_at is None


async def test_register_503_when_mail_fails_on_prod(client, monkeypatch, session):
    from app.mail import MailNotConfigured

    async def _boom(session, user, base):
        raise MailNotConfigured("no key")

    monkeypatch.setattr(auth_routes, "send_verification", _boom)
    r = await client.post("/auth/register", json=CREDS)
    assert r.status_code == 503
    # Nothing half-created: the address is free to try again.
    assert await session.scalar(select(User).where(User.email == CREDS["email"])) is None


async def test_google_still_signs_in_without_a_link(client, monkeypatch, outbox):
    monkeypatch.setattr(settings, "google_client_id", "cid")

    async def _fake(credential, client_id):
        return {"sub": "g-1", "email": "g@example.com", "email_verified": True, "name": "G", "picture": None}

    monkeypatch.setattr(auth_routes, "verify_google_id_token", _fake)
    r = await client.post("/auth/google", json={"credential": "tok"})
    assert r.status_code == 200 and "access" in r.json()
    assert outbox == []


async def test_link_follows_the_requesting_origin(client, outbox, monkeypatch):
    """Two origins serve the app; a session does not cross them, so the link
    must land where the person registered — if that origin is ours."""
    monkeypatch.setattr(settings, "cors_origins", "https://radar.test,https://radar.vercel.test")
    r = await client.post(
        "/auth/register", json=CREDS, headers={"Origin": "https://radar.vercel.test"}
    )
    assert r.status_code == 202
    assert "https://radar.vercel.test/verify-email?token=" in outbox[0][2]

    r = await client.post(
        "/auth/forgot-password", json=CREDS, headers={"Origin": "https://evil.test"}
    )
    assert r.status_code == 200
    assert "https://radar.test/reset-password?token=" in outbox[1][2]

"""Password hashing + JWT encode/decode (app/auth/security.py)."""
from __future__ import annotations

import pytest

from app.auth import security
from app.config import settings
from app.models import User


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(settings, "auth_jwt_secret", "unit-test-secret")


def test_password_hash_roundtrip():
    h = security.hash_password("hunter2000!")
    assert h != "hunter2000!"
    assert security.verify_password(h, "hunter2000!")
    assert not security.verify_password(h, "wrong-password")
    # A garbage hash never raises, just returns False.
    assert not security.verify_password("not-a-hash", "whatever")


def test_access_token_roundtrip():
    tok = security.encode_access(User(id=42, role="admin"))
    claims = security.decode_access(tok)
    assert claims["sub"] == "42"
    assert claims["role"] == "admin"
    assert claims["type"] == "access"


def test_wrong_token_type_rejected():
    refresh = security.encode_refresh(User(id=1, role="user"))
    with pytest.raises(security.AuthError):
        security.decode_access(refresh)
    # ...and vice-versa.
    access = security.encode_access(User(id=1, role="user"))
    with pytest.raises(security.AuthError):
        security.decode_refresh(access)


def test_tampered_token_rejected():
    tok = security.encode_access(User(id=1, role="user"))
    with pytest.raises(security.AuthError):
        security.decode_access(tok + "tampered")


def test_expired_token_rejected(monkeypatch):
    monkeypatch.setattr(settings, "auth_access_ttl_minutes", -1)  # already expired
    tok = security.encode_access(User(id=1, role="user"))
    with pytest.raises(security.AuthError):
        security.decode_access(tok)


def test_prod_without_secret_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "auth_jwt_secret", "")
    monkeypatch.setattr(settings, "environment", "production")
    with pytest.raises(security.AuthError):
        security.encode_access(User(id=1, role="user"))

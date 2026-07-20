"""Password hashing (argon2) + our own JWT access/refresh tokens (HS256).

The signing key comes from settings.auth_jwt_secret. In development ONLY, an
empty secret falls back to a fixed insecure constant so the local app runs with
zero setup — this fallback is refused outside development so prod can never
issue tokens under a guessable key.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

from ..config import settings
from ..models import User

_hasher = PasswordHasher()

_ALGO = "HS256"
# Fixed insecure key used ONLY in local development when AUTH_JWT_SECRET is unset
# (see settings.auth_configured). Never reachable in prod — _signing_key refuses.
_DEV_INSECURE_KEY = "dev-insecure-key-do-not-use-in-production"


class AuthError(Exception):
    """A token failed to decode/verify, or was the wrong type."""


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def _signing_key() -> str:
    if settings.auth_jwt_secret:
        return settings.auth_jwt_secret
    if settings.environment == "development":
        return _DEV_INSECURE_KEY
    # Fail closed: never sign/verify with the dev key outside development.
    raise AuthError("AUTH_JWT_SECRET is not configured")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _encode(user: User, token_type: str, ttl: timedelta) -> str:
    now = _now()
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, _signing_key(), algorithm=_ALGO)


def encode_access(user: User) -> str:
    return _encode(user, "access", timedelta(minutes=settings.auth_access_ttl_minutes))


def encode_refresh(user: User) -> str:
    return _encode(user, "refresh", timedelta(days=settings.auth_refresh_ttl_days))


def decode_token(token: str, expected_type: str) -> dict:
    """Decode + verify signature/expiry, and assert the token `type`. Raises
    AuthError on any failure (bad signature, expired, wrong type)."""
    try:
        claims = jwt.decode(token, _signing_key(), algorithms=[_ALGO])
    except jwt.PyJWTError as exc:
        raise AuthError(str(exc)) from exc
    if claims.get("type") != expected_type:
        raise AuthError(f"expected {expected_type} token, got {claims.get('type')!r}")
    return claims


def decode_access(token: str) -> dict:
    return decode_token(token, "access")


def decode_refresh(token: str) -> dict:
    return decode_token(token, "refresh")

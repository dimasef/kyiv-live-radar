"""FastAPI auth dependencies: current-user (required / optional) + admin gate.

Bearer-token based (Authorization: Bearer <access>), so NO ASGI middleware is
added — the raw CORS wrap in app/main.py and its OTel ordering are untouched.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import User
from .security import AuthError, decode_access


def _bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


async def _load_user_from_token(token: str, session: AsyncSession) -> Optional[User]:
    try:
        claims = decode_access(token)
    except AuthError:
        return None
    try:
        user_id = int(claims["sub"])
    except (KeyError, ValueError, TypeError):
        return None
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


async def get_current_user(
    authorization: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Require a valid access token → the active User, else 401."""
    token = _bearer_token(authorization)
    user = await _load_user_from_token(token, session) if token else None
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


async def get_optional_user(
    authorization: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_session),
) -> Optional[User]:
    """Return the User when a valid token is present, else None (never raises).
    For endpoints that behave differently when logged in but stay public."""
    token = _bearer_token(authorization)
    if not token:
        return None
    return await _load_user_from_token(token, session)


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """401 when unauthenticated (via get_current_user), 403 when authed-but-not-admin."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user

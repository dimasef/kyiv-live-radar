"""FastAPI auth dependencies: current-user (required / optional) + admin gate.

Bearer-token based (Authorization: Bearer <access>), so NO ASGI middleware is
added — the raw CORS wrap in app/main.py and its OTel ordering are untouched.
"""
from __future__ import annotations

from datetime import timedelta

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_session
from ..domain.presence import needs_stamp
from ..models import ADMIN_ROLES, IMPACT_ROLES, User, utcnow
from .security import AuthError, decode_access


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


async def _load_user_from_token(token: str, session: AsyncSession) -> User | None:
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


async def _stamp_last_seen(session: AsyncSession, user: User) -> None:
    """Record that this user is active, at most once per throttle window.

    Committed here rather than left for the route: most authenticated routes are
    reads that never commit, and a pending dirty row would then be flushed at an
    arbitrary later point (or rolled back with the route's own error).
    """
    now = utcnow()
    if not needs_stamp(user.last_seen_at, now, timedelta(seconds=settings.presence_stamp_throttle_seconds)):
        return
    user.last_seen_at = now
    await session.commit()


async def get_current_user(
    authorization: str | None = Header(None),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Require a valid access token → the active User, else 401."""
    token = _bearer_token(authorization)
    user = await _load_user_from_token(token, session) if token else None
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    await _stamp_last_seen(session, user)
    return user


async def get_optional_user(
    authorization: str | None = Header(None),
    session: AsyncSession = Depends(get_session),
) -> User | None:
    """Return the User when a valid token is present, else None (never raises).
    For endpoints that behave differently when logged in but stay public."""
    token = _bearer_token(authorization)
    if not token:
        return None
    return await _load_user_from_token(token, session)


async def require_impact_access(user: User = Depends(get_current_user)) -> User:
    """401 unauthenticated, 403 for anyone an operator has not vouched for.

    Guards the one route that publishes strike locations while a raid is still
    running (models.IMPACT_ROLES). Deliberately its own dependency rather than a
    parameter on require_admin: this is not console access, and the day someone
    widens what 'admin' means, that must not silently widen this too."""
    if user.role not in IMPACT_ROLES:
        raise HTTPException(status_code=403, detail="Impact access only")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """401 when unauthenticated (via get_current_user), 403 when authed-but-not-admin.
    Both 'admin' and the manual 'admin_g' role are admins (models.ADMIN_ROLES)."""
    if user.role not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin only")
    return user

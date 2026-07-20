"""Auth endpoints: email/password + Google + Telegram → our JWT token pair.

All routes 503 until AUTH_JWT_SECRET is configured (dev falls back to an
insecure key). Each SSO route additionally 503s until ITS provider is set up.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import get_current_user
from ..auth.providers.google import GoogleAuthError, verify_google_id_token
from ..auth.providers.telegram import TelegramAuthError, verify_telegram_login
from ..auth.security import (
    AuthError,
    decode_refresh,
    encode_access,
    hash_password,
    verify_password,
)
from ..auth.service import (
    get_or_create_user_for_identity,
    issue_tokens,
    resolve_and_set_role,
    touch_login,
)
from ..config import settings
from ..db import get_session
from ..models import OAuthIdentity, User
from ..schemas import (
    AccessTokenOut,
    GoogleAuthIn,
    LoginIn,
    RefreshIn,
    RegisterIn,
    TelegramAuthIn,
    TokenPairOut,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _require_auth_configured() -> None:
    if not settings.auth_configured:
        raise HTTPException(status_code=503, detail="Authentication is not configured")


async def _user_out(session: AsyncSession, user: User) -> UserOut:
    providers: list[str] = ["password"] if user.password_hash else []
    linked = await session.scalars(
        select(OAuthIdentity.provider).where(OAuthIdentity.user_id == user.id)
    )
    providers.extend(sorted(set(linked)))
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        role=user.role,
        providers=providers,
    )


async def _finish_login(session: AsyncSession, user: User) -> TokenPairOut:
    """Re-resolve role, stamp login time, commit, mint tokens — the tail shared
    by every provider."""
    await resolve_and_set_role(session, user)
    await touch_login(session, user)
    await session.commit()
    access, refresh = issue_tokens(user)
    return TokenPairOut(access=access, refresh=refresh, user=await _user_out(session, user))


@router.post("/register", response_model=TokenPairOut)
async def register(body: RegisterIn, session: AsyncSession = Depends(get_session)):
    _require_auth_configured()
    email = body.email.lower()
    if await session.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=email,
        email_verified=False,  # password accounts are unverified; never admin via email
        password_hash=hash_password(body.password),
        display_name=body.display_name,
    )
    session.add(user)
    await session.flush()
    return await _finish_login(session, user)


@router.post("/login", response_model=TokenPairOut)
async def login(body: LoginIn, session: AsyncSession = Depends(get_session)):
    _require_auth_configured()
    user = await session.scalar(select(User).where(User.email == body.email.lower()))
    # Uniform 401 whether the email is unknown or the password is wrong — no
    # account enumeration.
    if user is None or not user.password_hash or not verify_password(user.password_hash, body.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    return await _finish_login(session, user)


@router.post("/refresh", response_model=AccessTokenOut)
async def refresh(body: RefreshIn, session: AsyncSession = Depends(get_session)):
    _require_auth_configured()
    try:
        claims = decode_refresh(body.refresh)
        user = await session.get(User, int(claims["sub"]))
    except (AuthError, KeyError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    # Re-resolve so an allowlist promotion/demotion reaches the new access token.
    await resolve_and_set_role(session, user)
    await session.commit()
    return AccessTokenOut(access=encode_access(user))


@router.post("/logout")
async def logout():
    """Stateless: the client discards its tokens. Endpoint exists for symmetry
    and a future server-side revocation hook."""
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
):
    return await _user_out(session, user)


@router.post("/google", response_model=TokenPairOut)
async def google_login(body: GoogleAuthIn, session: AsyncSession = Depends(get_session)):
    _require_auth_configured()
    if not settings.google_configured:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")
    try:
        profile = await verify_google_id_token(body.credential, settings.google_client_id)
    except GoogleAuthError:
        raise HTTPException(status_code=401, detail="Google verification failed")
    if not profile["email_verified"]:
        raise HTTPException(status_code=401, detail="Google email is not verified")
    email: Optional[str] = (profile.get("email") or "").lower() or None
    user = await get_or_create_user_for_identity(
        session,
        provider="google",
        provider_user_id=str(profile["sub"]),
        email=email,
        email_verified=True,
        display_name=profile.get("name"),
        avatar_url=profile.get("picture"),
        raw_profile=profile,
    )
    return await _finish_login(session, user)


@router.post("/telegram", response_model=TokenPairOut)
async def telegram_login(body: TelegramAuthIn, session: AsyncSession = Depends(get_session)):
    _require_auth_configured()
    if not settings.telegram_login_configured:
        raise HTTPException(status_code=503, detail="Telegram sign-in is not configured")
    # Verify against EXACTLY the fields the widget signed (all present fields,
    # minus `hash`). extra='allow' on the schema preserves any we don't model.
    payload = body.model_dump(exclude_none=True)
    received_hash = payload.pop("hash", "")
    try:
        verify_telegram_login(payload, received_hash, settings.telegram_login_bot_token)
    except TelegramAuthError:
        raise HTTPException(status_code=401, detail="Telegram verification failed")
    name = body.first_name + (f" {body.last_name}" if body.last_name else "")
    user = await get_or_create_user_for_identity(
        session,
        provider="telegram",
        provider_user_id=str(body.id),
        email=None,  # Telegram gives no email — admin for TG users is id-based only
        email_verified=False,
        display_name=name or body.username,
        avatar_url=body.photo_url,
        raw_profile=payload,
    )
    return await _finish_login(session, user)

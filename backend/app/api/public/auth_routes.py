"""Auth endpoints: email/password + Google + Telegram → our JWT token pair.

All routes 503 until AUTH_JWT_SECRET is configured (dev falls back to an
insecure key). Each SSO route additionally 503s until ITS provider is set up.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.avatar import AvatarError, validate_avatar_data_url
from ...auth.deps import get_current_user
from ...auth.providers.google import GoogleAuthError, verify_google_id_token
from ...auth.providers.telegram import TelegramAuthError, verify_telegram_login
from ...auth.security import hash_password, verify_password
from ...auth.service import (
    get_or_create_user_for_identity,
    issue_tokens,
    resolve_and_set_role,
    revoke_refresh,
    rotate_refresh,
    touch_login,
)
from ...config import settings
from ...db import get_session
from ...models import OAuthIdentity, User
from ...schemas import (
    AccessTokenOut,
    GoogleAuthIn,
    LoginIn,
    LogoutIn,
    MeUpdateIn,
    RefreshIn,
    RegisterIn,
    TelegramAuthIn,
    TokenPairOut,
    UserOut,
)
from ..ratelimit import enforce, limiter, per_ip

router = APIRouter(prefix="/auth", tags=["auth"])


def _auth_ip_limit():
    return per_ip("auth", settings.auth_rate_limit_per_minute)


def _email_key(email: str) -> str:
    return f"auth-login-email:{email}"


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
        gamification=user.gamification,
        share_presence=user.share_presence,
    )


async def _finish_login(session: AsyncSession, user: User) -> TokenPairOut:
    """Re-resolve role, stamp login time, commit, mint tokens — the tail shared
    by every provider."""
    await resolve_and_set_role(session, user)
    await touch_login(session, user)
    access, refresh = await issue_tokens(session, user)
    await session.commit()
    return TokenPairOut(access=access, refresh=refresh, user=await _user_out(session, user))


@router.post("/register", response_model=TokenPairOut, dependencies=[Depends(_auth_ip_limit())])
async def register(body: RegisterIn, session: AsyncSession = Depends(get_session)):
    _require_auth_configured()
    email = body.email.lower()
    if await session.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=email,
        email_verified=False,  # password accounts are unverified; never admin via email
        # argon2 is ~35 ms of CPU: off the event loop, or a signup flood stalls
        # every WebSocket broadcast (same reason pipeline/webpush.py threads).
        password_hash=await asyncio.to_thread(hash_password, body.password),
        display_name=body.display_name,
    )
    session.add(user)
    await session.flush()
    return await _finish_login(session, user)


@router.post("/login", response_model=TokenPairOut, dependencies=[Depends(_auth_ip_limit())])
async def login(body: LoginIn, session: AsyncSession = Depends(get_session)):
    _require_auth_configured()
    email = body.email.lower()
    # Per-email cap on FAILED attempts, on top of the per-IP one: it holds when
    # the guesses come from many addresses. A success clears it.
    enforce(
        _email_key(email),
        settings.auth_login_attempts_per_email,
        settings.auth_login_lockout_minutes * 60,
    )
    user = await session.scalar(select(User).where(User.email == email))
    ok = (
        user is not None
        and bool(user.password_hash)
        and await asyncio.to_thread(verify_password, user.password_hash, body.password)
    )
    # Uniform 401 whether the email is unknown or the password is wrong — no
    # account enumeration.
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    limiter.forget(_email_key(email))
    return await _finish_login(session, user)


@router.post("/refresh", response_model=AccessTokenOut, dependencies=[Depends(_auth_ip_limit())])
async def refresh(body: RefreshIn, session: AsyncSession = Depends(get_session)):
    _require_auth_configured()
    user = await rotate_refresh(session, body.refresh)
    if user is None or not user.is_active:
        # A reuse of a revoked token has already revoked the family inside
        # rotate_refresh; that has to persist even though the caller gets 401.
        await session.commit()
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    # Re-resolve so an allowlist promotion/demotion reaches the new access token.
    await resolve_and_set_role(session, user)
    access, refresh = await issue_tokens(session, user)
    await session.commit()
    return AccessTokenOut(access=access, refresh=refresh)


@router.post("/logout")
async def logout(body: LogoutIn | None = None, session: AsyncSession = Depends(get_session)):
    """Revoke the refresh token; the client discards both. The access token
    stays valid until it expires (auth_access_ttl_minutes)."""
    if body is not None and body.refresh:
        await revoke_refresh(session, body.refresh)
        await session.commit()
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
):
    return await _user_out(session, user)


@router.patch("/me", response_model=UserOut)
async def update_me(
    body: MeUpdateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Edit your own profile. Only the fields actually present in the request
    are touched, so sending just an avatar can't blank a display name."""
    fields = body.model_fields_set
    if "display_name" in fields:
        name = (body.display_name or "").strip()
        user.display_name = name or None
    if "avatar_url" in fields:
        if body.avatar_url is None:
            user.avatar_url = None
        else:
            try:
                user.avatar_url = validate_avatar_data_url(body.avatar_url)
            except AvatarError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return await _user_out(session, user)


@router.post("/google", response_model=TokenPairOut, dependencies=[Depends(_auth_ip_limit())])
async def google_login(body: GoogleAuthIn, session: AsyncSession = Depends(get_session)):
    _require_auth_configured()
    if not settings.google_configured:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")
    try:
        profile = await verify_google_id_token(body.credential, settings.google_client_id)
    except GoogleAuthError:
        raise HTTPException(status_code=401, detail="Google verification failed") from None
    if not profile["email_verified"]:
        raise HTTPException(status_code=401, detail="Google email is not verified")
    email: str | None = (profile.get("email") or "").lower() or None
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


@router.post("/telegram", response_model=TokenPairOut, dependencies=[Depends(_auth_ip_limit())])
async def telegram_login(body: TelegramAuthIn, session: AsyncSession = Depends(get_session)):
    _require_auth_configured()
    if not settings.telegram_login_configured:
        raise HTTPException(status_code=503, detail="Telegram sign-in is not configured")
    # Verify against EXACTLY the fields the widget signed (all present fields,
    # minus `hash`). extra='allow' on the schema preserves any we don't model.
    payload = body.model_dump(exclude_none=True)
    received_hash = payload.pop("hash", "")
    try:
        verify_telegram_login(
            payload,
            received_hash,
            settings.telegram_login_bot_token,
            max_age_s=settings.auth_telegram_max_age_s,
        )
    except TelegramAuthError:
        raise HTTPException(status_code=401, detail="Telegram verification failed") from None
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

"""Auth endpoints: email/password (+ mailed verification/reset links) and
Google → our JWT token pair.

All routes 503 until AUTH_JWT_SECRET is configured (dev falls back to an
insecure key). Google additionally 503s until its client id is set, and the
routes that send mail 503 on a deployed host without RESEND_API_KEY.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.avatar import AvatarError, validate_avatar_data_url
from ...auth.deps import get_current_user
from ...auth.providers.google import GoogleAuthError, verify_google_id_token
from ...auth.security import hash_password, verify_password
from ...auth.service import (
    get_or_create_user_for_identity,
    issue_tokens,
    resolve_and_set_role,
    revoke_all_refresh,
    revoke_refresh,
    rotate_refresh,
    touch_login,
)
from ...auth.verification import (
    consume_email_token,
    link_base,
    send_password_reset,
    send_verification,
)
from ...config import settings
from ...db import get_session
from ...mail import MailError, MailNotConfigured
from ...models import OAuthIdentity, User
from ...schemas import (
    AccessTokenOut,
    EmailOnlyIn,
    GoogleAuthIn,
    LoginIn,
    LogoutIn,
    MeUpdateIn,
    OkOut,
    RefreshIn,
    RegisterIn,
    RegisterOut,
    ResetPasswordIn,
    TokenPairOut,
    UserOut,
    VerifyEmailIn,
)
from ..ratelimit import enforce, limiter, per_ip

router = APIRouter(prefix="/auth", tags=["auth"])


def _auth_ip_limit():
    return per_ip("auth", settings.auth_rate_limit_per_minute)


def _email_key(email: str) -> str:
    return f"auth-login-email:{email}"


def _base(request: Request) -> str:
    return link_base(request.headers.get("origin"))


def _mail_key(scope: str, email: str) -> str:
    return f"auth-mail-{scope}:{email}"


async def _send_or_503(session: AsyncSession, coro) -> None:
    """Run a mail send; a provider failure is the caller's 503, not a 500, and
    nothing the route flushed before it (a fresh account, a token row) stays."""
    try:
        await coro
    except MailNotConfigured:
        await session.rollback()
        raise HTTPException(status_code=503, detail="Email delivery is not configured") from None
    except MailError:
        await session.rollback()
        raise HTTPException(status_code=503, detail="Could not send the email") from None


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


@router.post(
    "/register",
    response_model=RegisterOut | TokenPairOut,
    status_code=202,
    dependencies=[Depends(_auth_ip_limit())],
)
async def register(
    body: RegisterIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    """Create the account and mail a verification link. No tokens until the
    link is used — the address has to be proven first (an unverified account
    could otherwise squat someone else's email; see auth.service merge rules)."""
    _require_auth_configured()
    email = body.email.lower()
    if await session.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=email,
        email_verified=False,
        # argon2 is ~35 ms of CPU: off the event loop, or a signup flood stalls
        # every WebSocket broadcast (same reason pipeline/webpush.py threads).
        password_hash=await asyncio.to_thread(hash_password, body.password),
        display_name=body.display_name,
    )
    session.add(user)
    await session.flush()
    if not settings.email_verification_enabled:
        response.status_code = 200
        return await _finish_login(session, user)
    await _send_or_503(session, send_verification(session, user, _base(request)))
    await session.commit()
    return RegisterOut(email=email)


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
    if settings.email_verification_enabled and not user.email_verified:
        # The password matched, so this is the account's owner-or-registrant
        # asking; the UI turns the code into a "resend the link" offer.
        raise HTTPException(status_code=403, detail={"code": "email_unverified"})
    limiter.forget(_email_key(email))
    return await _finish_login(session, user)


@router.post("/verify-email", response_model=TokenPairOut, dependencies=[Depends(_auth_ip_limit())])
async def verify_email(body: VerifyEmailIn, session: AsyncSession = Depends(get_session)):
    """Prove the address with the mailed token; signs the user in on success."""
    _require_auth_configured()
    user = await consume_email_token(session, body.token, "verify")
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail={"code": "bad_token"})
    user.email_verified = True
    return await _finish_login(session, user)


@router.post("/resend-verification", response_model=OkOut, dependencies=[Depends(_auth_ip_limit())])
async def resend_verification(
    body: EmailOnlyIn, request: Request, session: AsyncSession = Depends(get_session)
):
    """Always 200: whether the address exists is not for the caller to learn."""
    _require_auth_configured()
    email = body.email.lower()
    enforce(_mail_key("verify", email), settings.auth_mail_per_email, 600)
    user = await session.scalar(select(User).where(User.email == email))
    if user is not None and user.is_active and not user.email_verified:
        await _send_or_503(session, send_verification(session, user, _base(request)))
        await session.commit()
    return OkOut()


@router.post("/forgot-password", response_model=OkOut, dependencies=[Depends(_auth_ip_limit())])
async def forgot_password(
    body: EmailOnlyIn, request: Request, session: AsyncSession = Depends(get_session)
):
    """Always 200. The reset link goes to the address's real owner, which is
    also how they reclaim an email someone registered without verifying."""
    _require_auth_configured()
    email = body.email.lower()
    enforce(_mail_key("reset", email), settings.auth_mail_per_email, 600)
    user = await session.scalar(select(User).where(User.email == email))
    if user is not None and user.is_active:
        await _send_or_503(session, send_password_reset(session, user, _base(request)))
        await session.commit()
    return OkOut()


@router.post("/reset-password", response_model=TokenPairOut, dependencies=[Depends(_auth_ip_limit())])
async def reset_password(body: ResetPasswordIn, session: AsyncSession = Depends(get_session)):
    """Set a new password from the mailed token. Using the link proves the
    address, so it also verifies it; every other session is signed out."""
    _require_auth_configured()
    user = await consume_email_token(session, body.token, "reset")
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail={"code": "bad_token"})
    user.password_hash = await asyncio.to_thread(hash_password, body.password)
    user.email_verified = True
    await revoke_all_refresh(session, user.id)
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

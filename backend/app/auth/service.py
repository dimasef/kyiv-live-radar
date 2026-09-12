"""Auth service layer: role resolution, provider-identity linking, token issue.

Shared by every sign-in route (email/password, Google) so the account-linking
and role rules live in exactly one place.
"""
from __future__ import annotations

import logging

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import MANUAL_ROLES, OAuthIdentity, RefreshToken, RoleSource, User, utcnow
from ..timeutil import naive
from .security import AuthError, decode_refresh, encode_access, encode_refresh

log = logging.getLogger("auth")


def role_for(verified_email: str | None) -> str:
    """Resolve a role from the env allowlist. Only a VERIFIED email counts —
    one Google vouched for, or one whose owner clicked our verification link."""
    if verified_email and verified_email.lower() in settings.admin_email_list:
        return "admin"
    return "user"


def role_source_for(user: User) -> RoleSource:
    """WHY this user's role is what it is — see models.RoleSource. Pure, so a
    whole page of users costs no extra query; lives next to `role_for` and
    `resolve_and_set_role` because all three must agree on the allowlist."""
    if user.role in MANUAL_ROLES:
        return "manual"
    if role_for(user.email if user.email_verified else None) == "admin":
        return "allowlist"
    return "default"


async def resolve_and_set_role(session: AsyncSession, user: User) -> None:
    """Recompute and persist user.role from the allowlist. Called on every
    login so a change to the allowlist takes effect on the user's next sign-in.

    A role in `MANUAL_ROLES` is stored intent, not derived state — nothing in the
    env computes it — so it is preserved as-is. Recomputing would clobber it back
    to admin/user on the next login, which is exactly what it did to 'observer'
    until 2026-09-08: the only role that unlocks the consequence layer could be
    granted from the console and then lost at the person's very next sign-in."""
    if user.role in MANUAL_ROLES:
        return
    user.role = role_for(user.email if user.email_verified else None)


async def get_or_create_user_for_identity(
    session: AsyncSession,
    *,
    provider: str,
    provider_user_id: str,
    email: str | None,
    email_verified: bool,
    display_name: str | None,
    avatar_url: str | None,
    raw_profile: dict | None,
) -> User:
    """Map an SSO identity to a User: existing identity → its user; else link to
    a user with the SAME verified email (account merge); else create a new user.
    Adds the identity row when it's new."""
    identity = await session.scalar(
        select(OAuthIdentity).where(
            OAuthIdentity.provider == provider,
            OAuthIdentity.provider_user_id == provider_user_id,
        )
    )
    if identity is not None:
        user = await session.get(User, identity.user_id)
        identity.raw_profile = raw_profile
        if email:
            identity.email = email
        # Backfill missing profile bits without clobbering user edits.
        if user is not None:
            if not user.display_name and display_name:
                user.display_name = display_name
            if not user.avatar_url and avatar_url:
                user.avatar_url = avatar_url
        return user

    user: User | None = None
    if email and email_verified:
        user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email if email_verified else None,
            email_verified=bool(email and email_verified),
            display_name=display_name,
            avatar_url=avatar_url,
        )
        session.add(user)
        await session.flush()  # assign user.id for the FK below
    else:
        # Merging a verified SSO identity onto an existing account: the provider
        # now vouches for the email, and fill any profile gaps.
        if email_verified and not user.email_verified and user.password_hash:
            # Nobody has proven they own this email until now, so the password
            # on the row may have been set by whoever registered the address
            # first — a pre-registration hijack. The SSO login is the first
            # trusted claim; the unverified password is dropped with it.
            log.warning("auth: dropping unverified password on SSO merge for user %s", user.id)
            user.password_hash = None
        if email_verified:
            user.email_verified = True
        if not user.display_name and display_name:
            user.display_name = display_name
        if not user.avatar_url and avatar_url:
            user.avatar_url = avatar_url

    session.add(
        OAuthIdentity(
            user_id=user.id,
            provider=provider,
            provider_user_id=provider_user_id,
            email=email,
            raw_profile=raw_profile,
        )
    )
    return user


async def issue_tokens(session: AsyncSession, user: User) -> tuple[str, str]:
    """Return (access, refresh) for a user, registering the refresh token's
    `jti` so it can later be rotated or revoked. Caller commits."""
    minted = encode_refresh(user)
    session.add(RefreshToken(user_id=user.id, jti=minted.jti, expires_at=minted.expires_at))
    return encode_access(user), minted.token


async def rotate_refresh(session: AsyncSession, token: str) -> User | None:
    """Consume a refresh token: verify it, revoke its row, and return the user
    it belongs to (None when it is invalid, unknown, expired or revoked).

    A token that was already revoked is treated as stolen: its whole family for
    that user is revoked, so the legitimate holder and the thief both have to
    sign in again. Caller mints the replacement pair and commits."""
    try:
        claims = decode_refresh(token)
        user_id = int(claims["sub"])
        jti = str(claims["jti"])
    except (AuthError, KeyError, ValueError, TypeError):
        return None
    row = await session.scalar(select(RefreshToken).where(RefreshToken.jti == jti))
    now = naive(utcnow())
    if row is None or row.user_id != user_id:
        return None
    if row.revoked_at is not None:
        log.warning("auth: reuse of a revoked refresh token for user %s — revoking all", user_id)
        await revoke_all_refresh(session, user_id)
        return None
    if naive(row.expires_at) <= now:
        return None
    row.revoked_at = now
    await session.execute(
        delete(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.expires_at < now)
    )
    return await session.get(User, user_id)


async def revoke_refresh(session: AsyncSession, token: str) -> None:
    """Logout: end this one refresh token. A malformed or foreign token is a
    silent no-op — logout must never fail."""
    try:
        claims = decode_refresh(token)
        jti = str(claims["jti"])
    except (AuthError, KeyError, ValueError, TypeError):
        return
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.jti == jti, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


async def revoke_all_refresh(session: AsyncSession, user_id: int) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


async def touch_login(session: AsyncSession, user: User) -> None:
    user.last_login_at = utcnow()

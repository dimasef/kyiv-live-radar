"""Auth service layer: role resolution, provider-identity linking, token issue.

Shared by every provider route (email/password, Google, Telegram) so the
account-linking and role rules live in exactly one place.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import OAuthIdentity, User, utcnow
from .security import encode_access, encode_refresh


def role_for(verified_email: Optional[str], telegram_ids: list[int]) -> str:
    """Resolve a role from the env allowlists. An email only counts when it was
    VERIFIED by a provider — a self-registered password email is never trusted
    for admin. Telegram is matched by numeric id."""
    if verified_email and verified_email.lower() in settings.admin_email_list:
        return "admin"
    admin_tg = set(settings.admin_telegram_id_list)
    if any(tid in admin_tg for tid in telegram_ids):
        return "admin"
    return "user"


async def _telegram_ids_for(session: AsyncSession, user: User) -> list[int]:
    rows = await session.scalars(
        select(OAuthIdentity.provider_user_id).where(
            OAuthIdentity.user_id == user.id, OAuthIdentity.provider == "telegram"
        )
    )
    out: list[int] = []
    for raw in rows:
        try:
            out.append(int(raw))
        except (TypeError, ValueError):
            pass
    return out


async def resolve_and_set_role(session: AsyncSession, user: User) -> None:
    """Recompute and persist user.role from ALL of the user's admin signals
    (verified email + any linked Telegram id). Called on every login so a change
    to the allowlist takes effect on the user's next sign-in."""
    verified_email = user.email if user.email_verified else None
    telegram_ids = await _telegram_ids_for(session, user)
    user.role = role_for(verified_email, telegram_ids)


async def get_or_create_user_for_identity(
    session: AsyncSession,
    *,
    provider: str,
    provider_user_id: str,
    email: Optional[str],
    email_verified: bool,
    display_name: Optional[str],
    avatar_url: Optional[str],
    raw_profile: Optional[dict],
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

    user: Optional[User] = None
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


def issue_tokens(user: User) -> tuple[str, str]:
    """Return (access, refresh) for a user. Caller commits any role/timestamp
    changes; this is pure token minting."""
    return encode_access(user), encode_refresh(user)


async def touch_login(session: AsyncSession, user: User) -> None:
    user.last_login_at = utcnow()

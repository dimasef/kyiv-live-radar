"""Email-ownership proof: one-time tokens for address verification and password
reset, and the messages that carry them.

The raw token (32 random bytes, urlsafe) exists only in the link; the row keeps
its SHA-256, so a database read-out yields nothing usable. Issuing a new token
retires the user's earlier unused ones of the same purpose, and consuming one
marks it used — a link works exactly once.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from html import escape
from typing import Literal
from urllib.parse import quote

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..mail import send_email
from ..models import EmailToken, User, utcnow
from ..timeutil import naive

Purpose = Literal["verify", "reset"]


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def issue_email_token(session: AsyncSession, user: User, purpose: Purpose) -> str:
    """Retire the user's live tokens of this purpose and mint a fresh one.
    Returns the RAW token for the link; only its hash is stored."""
    now = utcnow()
    await session.execute(
        update(EmailToken)
        .where(
            EmailToken.user_id == user.id,
            EmailToken.purpose == purpose,
            EmailToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    ttl = (
        timedelta(hours=settings.auth_verify_ttl_hours)
        if purpose == "verify"
        else timedelta(minutes=settings.auth_reset_ttl_minutes)
    )
    raw = secrets.token_urlsafe(32)
    session.add(
        EmailToken(user_id=user.id, purpose=purpose, token_hash=_hash(raw), expires_at=now + ttl)
    )
    return raw


async def consume_email_token(session: AsyncSession, raw: str, purpose: Purpose) -> User | None:
    """Mark the token used and return its user — None for an unknown, spent,
    expired or wrong-purpose token (the caller answers the same way for all four)."""
    if not raw or len(raw) > 128:
        return None
    row = await session.scalar(select(EmailToken).where(EmailToken.token_hash == _hash(raw)))
    if row is None or row.purpose != purpose or row.used_at is not None:
        return None
    now = naive(utcnow())
    if naive(row.expires_at) <= now:
        return None
    row.used_at = now
    return await session.get(User, row.user_id)


def link_base(origin: str | None) -> str:
    """Where a mailed link should land. The app is served from two origins
    (the custom domain and the original vercel.app one, where installed PWAs
    still live), and a signed-in session does not cross them — so the link
    goes back to the origin the request came from, provided it is one of ours
    (the CORS allowlist), else to PUBLIC_APP_URL."""
    if origin and origin in settings.cors_origin_list:
        return origin
    return settings.public_app_url.rstrip("/")


def _link(base: str, path: str, token: str) -> str:
    return f"{base}{path}?token={quote(token, safe='')}"


async def send_verification(session: AsyncSession, user: User, base: str) -> None:
    assert user.email
    link = _link(base, "/verify-email", await issue_email_token(session, user, "verify"))
    hours = settings.auth_verify_ttl_hours
    text = (
        "Підтвердіть пошту для UA Live Radar — відкрийте посилання:\n\n"
        f"{link}\n\n"
        f"Посилання діє {hours} год. Якщо ви не реєструвалися, просто проігноруйте цей лист."
    )
    html = (
        "<p>Підтвердіть пошту для <b>UA Live Radar</b>:</p>"
        f'<p><a href="{escape(link)}">Підтвердити пошту</a></p>'
        f"<p>Посилання діє {hours} год. Якщо ви не реєструвалися, просто проігноруйте цей лист.</p>"
    )
    await send_email(user.email, "Підтвердіть пошту — UA Live Radar", text, html)


async def send_password_reset(session: AsyncSession, user: User, base: str) -> None:
    assert user.email
    link = _link(base, "/reset-password", await issue_email_token(session, user, "reset"))
    minutes = settings.auth_reset_ttl_minutes
    text = (
        "Ви запросили скидання пароля в UA Live Radar — відкрийте посилання:\n\n"
        f"{link}\n\n"
        f"Посилання діє {minutes} хв. Якщо це були не ви, проігноруйте цей лист — пароль не зміниться."
    )
    html = (
        "<p>Скидання пароля в <b>UA Live Radar</b>:</p>"
        f'<p><a href="{escape(link)}">Встановити новий пароль</a></p>'
        f"<p>Посилання діє {minutes} хв. Якщо це були не ви, проігноруйте цей лист — пароль не зміниться.</p>"
    )
    await send_email(user.email, "Скидання пароля — UA Live Radar", text, html)

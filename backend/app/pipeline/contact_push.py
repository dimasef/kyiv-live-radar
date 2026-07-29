"""Web Push for contact (friends) events — a new invite and its acceptance.

Piggybacks on whatever push subscriptions the target user already has (created
via the danger-near-home opt-in); a user with none simply relies on the in-app
badge. Called fire-and-forget-ish from the friends endpoints AFTER they commit,
and never raises — a failed push must not break adding a contact."""

from __future__ import annotations

import logging

from sqlalchemy import select

from ..config import settings
from ..models import PushSubscription, User
from .webpush import send_push

log = logging.getLogger("contact_push")


def _display(u: User) -> str:
    return u.display_name or u.email or "Хтось"


async def _notify(session, user_id: int, payload: dict) -> None:
    if not settings.push_configured:
        return
    try:
        subs = list(
            await session.scalars(
                select(PushSubscription).where(PushSubscription.user_id == user_id)
            )
        )
        if not subs:
            return
        for sub in subs:
            await send_push(session, sub, payload)
        await session.commit()  # persist any endpoint pruning send_push did
    except Exception:  # pragma: no cover - push must never break the contact action
        log.exception("contact push failed for user %s", user_id)


async def notify_contact_request(session, addressee_id: int, requester: User) -> None:
    """A new contact request landed — tell the addressee."""
    await _notify(
        session,
        addressee_id,
        {
            "kind": "contact-invite",
            "tag": f"klr-contact-invite-{requester.id}",
            "title": "Новий запит у контакти",
            "body": f"{_display(requester)} хоче додати вас у контакти.",
            "url": "/account",
        },
    )


async def notify_request_accepted(session, requester_id: int, accepter: User) -> None:
    """A contact request was accepted — tell whoever originally sent it."""
    await _notify(
        session,
        requester_id,
        {
            "kind": "contact-accepted",
            "tag": f"klr-contact-accepted-{accepter.id}",
            "title": "Запит у контакти прийнято",
            "body": f"{_display(accepter)} у ваших контактах.",
            "url": "/account",
        },
    )

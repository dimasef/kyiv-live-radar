"""Low-level Web Push send — shared by home_push (threat notifications) and
contact_push (contact-request notifications).

Signs the VAPID request off the event loop (pywebpush is synchronous) and prunes
a subscription whose endpoint the push service reports gone (404/410)."""

from __future__ import annotations

import asyncio
import json
import logging

from ..config import settings
from ..models import PushSubscription

log = logging.getLogger("webpush")

DEFAULT_TTL_S = 300


async def send_push(session, sub: PushSubscription, payload: dict, ttl: int = DEFAULT_TTL_S) -> None:
    from pywebpush import WebPushException, webpush  # deferred: optional at import time

    try:
        # webpush() is synchronous (requests under the hood) — never block the
        # event loop with it.
        await asyncio.to_thread(
            webpush,
            subscription_info={
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
            },
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_subject},
            ttl=ttl,
        )
    except WebPushException as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status in (404, 410):
            # The push service says this endpoint is gone (browser unsubscribed
            # or the registration expired) — drop the row.
            log.info("push endpoint gone (%s), deleting subscription %s", status, sub.id)
            await session.delete(sub)
        else:
            log.warning("web push failed (status=%s): %s", status, e)

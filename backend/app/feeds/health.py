"""Mutable listener health, read by GET /health so a dead/zombied connection
(weak point #7 — Telethon can disconnect and never retry, leaving FastAPI
serving stale data with no visible error) shows up in the API, not just logs.
"""

from __future__ import annotations

from datetime import datetime

from ..config import settings

_state: dict = {
    "connected": False,
    "last_message_at": None,  # datetime of the last live message actually received
    "last_error": None,
}


def get_status() -> dict:
    return dict(_state)


def feed_health(now: datetime, warn_minutes: int) -> bool | None:
    """Whether the live feed's CONNECTION is up — None when there's no real feed
    to judge (Telegram not configured; simulator/replay have nothing to monitor).

    Deliberately NOT silence-based. Spotter channels are legitimately quiet for
    hours between air raids, so "no messages lately" is a calm sky, not a fault —
    the old `last_message_at` + warn-window check cried «Втрачено зʼєднання» on
    every quiet night. A genuinely dead session surfaces as connected=False
    instead: the listener resets that flag on any disconnect/exception, and the
    watchdog force-reconnects a zombie ("connected" but silent) stream within
    listener_watchdog_silence_minutes — flipping this False if it can't recover.

    `now`/`warn_minutes` are unused now but kept in the signature (both callers
    pass them) so a future soft "quiet for a long time" hint could reuse them
    without another interface change. Shared by GET /health and sweeper.py.
    """
    if not settings.telegram_enabled:
        return None
    return _state["connected"]

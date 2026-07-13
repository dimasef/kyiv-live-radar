"""Mutable listener health, read by GET /health so a dead/zombied connection
(weak point #7 — Telethon can disconnect and never retry, leaving FastAPI
serving stale data with no visible error) shows up in the API, not just logs.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..config import settings
from ..timeutil import within

_state: dict = {
    "connected": False,
    "last_message_at": None,  # datetime of the last live message actually received
    "last_error": None,
}


def get_status() -> dict:
    return dict(_state)


def feed_health(now: datetime, warn_minutes: int) -> bool | None:
    """Whether the live feed looks healthy — None when there's no real feed
    to judge (Telegram not configured; simulator/replay modes have nothing
    to monitor here). False when disconnected, or connected but silent for
    longer than `warn_minutes`. `last_message_at` is only set by a LIVE
    message (never by the startup backfill), so a freshly-connected session
    with no live traffic yet reads as healthy rather than stale — only "was
    receiving, then stopped" is evidence of a real problem. Shared by
    GET /health (hydration) and sweeper.py (the periodic push on change).
    """
    if not settings.telegram_enabled:
        return None
    if not _state["connected"]:
        return False
    if _state["last_message_at"] is None:
        return True
    return within(_state["last_message_at"], now, timedelta(minutes=warn_minutes))

"""Shared tz-tolerant time-window helpers."""

from __future__ import annotations

from datetime import datetime, timedelta


def within(a: datetime, b: datetime, gap: timedelta) -> bool:
    """tz-tolerant recency/gap check (SQLite returns naive UTC; utcnow() is aware)."""
    an = a.replace(tzinfo=None) if a.tzinfo is not None else a
    bn = b.replace(tzinfo=None) if b.tzinfo is not None else b
    return abs((bn - an).total_seconds()) <= gap.total_seconds()

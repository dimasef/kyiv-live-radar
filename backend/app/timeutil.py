"""Shared tz-tolerant time-window helpers."""

from __future__ import annotations

from datetime import datetime, timedelta


def naive(dt: datetime) -> datetime:
    """Normalize to naive UTC for comparisons. Rows loaded from SQLite come back
    naive, but an object added in the CURRENT session still carries its aware
    timestamp — max()/sorting/equality across the two raises TypeError (or
    miscounts) unless normalized."""
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def within(a: datetime, b: datetime, gap: timedelta) -> bool:
    """tz-tolerant recency/gap check (SQLite returns naive UTC; utcnow() is aware)."""
    return abs((naive(b) - naive(a)).total_seconds()) <= gap.total_seconds()

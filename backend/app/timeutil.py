"""Shared tz-tolerant time-window helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

KYIV = ZoneInfo("Europe/Kyiv")


def kyiv_local(dt: datetime, tz: ZoneInfo = KYIV) -> datetime:
    """Naive-UTC (or aware) datetime -> the same instant as aware local time.

    Everything is stored as UTC wall-clock (SQLite drops tzinfo on round-trip),
    but every operator-facing bucket — day, hour — must be Kyiv-local.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(tz)


def kyiv_date(dt: datetime, tz: ZoneInfo = KYIV) -> date:
    """The calendar date `dt` falls on in `tz`."""
    return kyiv_local(dt, tz).date()


def naive(dt: datetime) -> datetime:
    """Normalize to naive UTC for comparisons. Rows loaded from SQLite come back
    naive, but an object added in the CURRENT session still carries its aware
    timestamp — max()/sorting/equality across the two raises TypeError (or
    miscounts) unless normalized."""
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def within(a: datetime, b: datetime, gap: timedelta) -> bool:
    """tz-tolerant recency/gap check (SQLite returns naive UTC; utcnow() is aware)."""
    return abs((naive(b) - naive(a)).total_seconds()) <= gap.total_seconds()

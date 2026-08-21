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


def from_kyiv_local(dt: datetime, tz: ZoneInfo = KYIV) -> datetime:
    """A naive wall-clock time GIVEN in Kyiv local time -> the same instant, UTC.

    The inverse of `kyiv_local`, for data that arrives stamped in local time with
    no offset (the alert-zone provider does exactly that). The one hour a year
    that repeats at the autumn DST fold resolves to the first pass — a siren
    timestamp an hour out once a year is not worth more machinery.
    """
    return dt.replace(tzinfo=tz).astimezone(UTC)


def kyiv_day_start(dt: datetime, tz: ZoneInfo = KYIV) -> datetime:
    """The instant Kyiv-local midnight began for the day `dt` falls on, as UTC.

    For "spent today" style windows: the operator's day is the Kyiv one, same as
    every other bucket in the app (see `kyiv_date`), not the UTC one.
    """
    local = kyiv_local(dt, tz).replace(hour=0, minute=0, second=0, microsecond=0)
    return from_kyiv_local(local.replace(tzinfo=None), tz)


def kyiv_month_start(dt: datetime, tz: ZoneInfo = KYIV) -> datetime:
    """As `kyiv_day_start`, for the first Kyiv-local day of `dt`'s month."""
    local = kyiv_local(dt, tz).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return from_kyiv_local(local.replace(tzinfo=None), tz)


def naive(dt: datetime) -> datetime:
    """Normalize to naive UTC for comparisons. Rows loaded from SQLite come back
    naive, but an object added in the CURRENT session still carries its aware
    timestamp — max()/sorting/equality across the two raises TypeError (or
    miscounts) unless normalized."""
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def within(a: datetime, b: datetime, gap: timedelta) -> bool:
    """tz-tolerant recency/gap check (SQLite returns naive UTC; utcnow() is aware)."""
    return abs((naive(b) - naive(a)).total_seconds()) <= gap.total_seconds()

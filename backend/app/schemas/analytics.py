"""Across-days statistics payloads for the journal's «Статистика» tab."""

from __future__ import annotations

from pydantic import BaseModel

from ..models import AlertDurationBucket, AnalyticsPeriod


class StatsDayOut(BaseModel):
    """One day, light: only what the period charts need. Deliberately NOT
    `JournalDayOut` — dropping alert_windows/district_ids keeps an "all time"
    response small, and the client groups these rows into weeks itself."""

    date: str  # Kyiv-local ISO date, YYYY-MM-DD
    attack_count: int = 0
    track_count: int = 0
    target_count: int = 0
    impact_count: int = 0
    alert_count: int = 0
    alert_seconds: int = 0
    alert_incomplete: bool = False
    type_counts: dict[str, int] = {}


class HourBucketOut(BaseModel):
    """One hour of the Kyiv-local day, aggregated over the whole period."""

    hour: int
    alert_minutes: int = 0
    # Share of this hour spent under a city alert, across the days the alert feed
    # covered (0..1) — normalized on alert_days_observed, never days_observed.
    alert_share: float = 0.0
    target_count: int = 0


class DurationBucketOut(BaseModel):
    """One bin of the alert-duration histogram; only complete windows counted."""

    bucket: AlertDurationBucket
    count: int = 0


class DistrictStatOut(BaseModel):
    """How often one district/approach town saw targets. `days` is the honest
    ranking key — `events` is raw sighting volume and rises with spotter
    chatter."""

    district_id: int
    days: int = 0
    events: int = 0
    impacts: int = 0


class StatsTotalsOut(BaseModel):
    attacks: int = 0
    tracks: int = 0
    targets: int = 0
    impacts: int = 0
    alerts: int = 0
    alert_seconds: int = 0
    longest_alert_seconds: int = 0
    # Some alert in the period was open/failsafe-closed → durations are a lower
    # bound and the UI prefixes "≥".
    alert_incomplete: bool = False
    active_days: int = 0
    quiet_streak_days: int = 0
    quiet_streak_from: str | None = None
    quiet_streak_to: str | None = None


class JournalStatsOut(BaseModel):
    """GET /journal/stats — one period, aggregated across its days.

    `alert_from_date`/`alert_days_observed` exist because the official alert feed
    was added after the spotter feed: every alert-derived rate is normalized on
    that narrower window, and the UI states it.
    """

    period: AnalyticsPeriod
    from_date: str
    to_date: str
    days_observed: int
    alert_from_date: str | None = None
    alert_days_observed: int = 0
    totals: StatsTotalsOut
    days: list[StatsDayOut] = []
    hours: list[HourBucketOut] = []  # always 24, ascending
    # Per-target-type totals and "in how many days did this type appear",
    # keyed by TARGET_TYPES.
    type_totals: dict[str, int] = {}
    type_days: dict[str, int] = {}
    alert_durations: list[DurationBucketOut] = []  # always 5, fixed order
    median_alert_seconds: int = 0
    mean_alert_seconds: int = 0
    districts: list[DistrictStatOut] = []  # most days first

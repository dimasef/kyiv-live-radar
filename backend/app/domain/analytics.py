"""Across-days aggregation for the journal's statistics tab (GET /journal/stats).

`journal.py` answers "how heavy was THIS day"; this module answers the questions
that only exist across days: at what hour of the Kyiv night do alerts and targets
actually happen, how long a typical alert lasts, which districts recur, how the
target mix shifts. Same contract as `journal.py` — pure, I/O-free, Kyiv-local
bucketing in Python, no DB date functions.

Two honesty constraints are encoded here rather than left to the UI:

* **The alert feed started later than the spotter feed.** Normalizing "share of
  time under alert" over the whole data range would silently dilute it with days
  that had no alert source at all, so alert rates use their own denominator
  (`alert_days_observed`, counted from `alert_start`).
* **An incomplete alert window has no duration.** Open and failsafe-closed
  alerts contribute 0 seconds and set `alert_incomplete` (same rule as
  `build_journal`), so a dead-listener "day-long siren" can never inflate a
  median or win "longest".

The intensity score stays on the client (`journalStats.ts` owns the weighting),
so this returns raw per-day rows and lets the frontend rank days itself.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from statistics import mean, median
from zoneinfo import ZoneInfo

from ..models import ALERT_DURATION_BUCKETS, TARGET_TYPES, AlertDurationBucket
from ..timeutil import KYIV, kyiv_date, kyiv_local, naive
from .journal import DayStat

# Upper bounds in minutes for every bucket but the last (which is open-ended).
_DURATION_BOUNDS_MINUTES = (30, 60, 120, 240)


def duration_bucket(seconds: int) -> AlertDurationBucket:
    """Which fixed histogram bin an alert of `seconds` falls in."""
    minutes = seconds / 60
    for i, bound in enumerate(_DURATION_BOUNDS_MINUTES):
        if minutes < bound:
            return ALERT_DURATION_BUCKETS[i]
    return ALERT_DURATION_BUCKETS[-1]


@dataclass
class HourBucket:
    hour: int  # 0-23, Kyiv local
    alert_minutes: int = 0  # minutes spent under a city alert in this hour, Σ over days
    # alert_minutes / (alert_days_observed * 60) — the share of that hour, across
    # observed days, spent under alert. Reads as "the chance of a siren at 23:00".
    alert_share: float = 0.0
    target_count: int = 0  # targets first sighted in this hour


@dataclass
class DistrictStat:
    district_id: int
    days: int = 0  # distinct Kyiv days with a sighting over this district
    events: int = 0  # raw sightings (spotter chatter inflates this — days don't)
    impacts: int = 0


@dataclass
class AnalyticsTotals:
    attacks: int = 0
    tracks: int = 0
    targets: int = 0
    impacts: int = 0
    alerts: int = 0
    alert_seconds: int = 0
    longest_alert_seconds: int = 0
    alert_incomplete: bool = False
    active_days: int = 0  # days with any activity at all
    # Longest run of consecutive days without a single city alert, within the
    # alert-coverage window (0 when there is no coverage yet).
    quiet_streak_days: int = 0
    quiet_streak_from: str | None = None
    quiet_streak_to: str | None = None


@dataclass
class AnalyticsStat:
    from_date: str
    to_date: str
    days_observed: int
    alert_from_date: str | None
    alert_days_observed: int
    totals: AnalyticsTotals
    hours: list[HourBucket]  # always 24, ascending
    type_totals: dict = field(default_factory=lambda: dict.fromkeys(TARGET_TYPES, 0))
    type_days: dict = field(default_factory=lambda: dict.fromkeys(TARGET_TYPES, 0))
    alert_durations: dict = field(default_factory=lambda: dict.fromkeys(ALERT_DURATION_BUCKETS, 0))
    median_alert_seconds: int = 0
    mean_alert_seconds: int = 0
    districts: list[DistrictStat] = field(default_factory=list)


def _has_activity(s: DayStat) -> bool:
    return bool(
        s.attack_count or s.target_count or s.impact_count or s.alert_count or s.district_count
    )


def _spread_alert_minutes(
    started_at: datetime,
    ended_at: datetime,
    hours: list[HourBucket],
    tz: ZoneInfo,
) -> None:
    """Add an alert window's minutes to the local hour-of-day bins it covers.

    Advances in absolute (UTC) time, one local-hour boundary per step, and reads
    the bin off the local clock. Doing the arithmetic in local time instead looks
    equivalent but is not: subtracting two datetimes that share a tzinfo gives the
    *wall-clock* difference, so the DST-shift days (23- and 25-hour) would silently
    lose or double an hour twice a year. Stepping by boundary rather than by minute
    keeps a day-long window at a couple of dozen iterations.
    """
    cursor = naive(started_at).replace(tzinfo=UTC)
    end = naive(ended_at).replace(tzinfo=UTC)
    while cursor < end:
        local = cursor.astimezone(tz)
        to_next_hour = timedelta(hours=1) - timedelta(
            minutes=local.minute, seconds=local.second, microseconds=local.microsecond
        )
        slice_end = min(cursor + to_next_hour, end)
        minutes = round((slice_end - cursor).total_seconds() / 60)
        if minutes:
            hours[local.hour].alert_minutes += minutes
        cursor = slice_end


def build_analytics(
    start: date,
    end: date,
    *,
    day_stats: list[DayStat],
    alert_windows,
    target_first_seen,
    district_events,
    alert_start: date | None,
    sentinel_district_id: int | None = None,
    tz: ZoneInfo = KYIV,
    top_districts: int = 12,
) -> AnalyticsStat:
    """Aggregate a period into one `AnalyticsStat`.

    `day_stats` comes from `build_journal` over the same range — every per-day
    number (and every dismissal/citywide/impact-privacy rule baked into it) is
    reused rather than recomputed.

    `alert_windows` is an iterable of `(started_at, ended_at, closed_reason)` for
    city alerts; `target_first_seen` of `(first_sighting_time, group_size)` per
    inbound track, so an hour's `target_count` counts targets the same way
    `DayStat.target_count` does; `district_events` of
    `(event_time, district_id, is_impact)` — the same triples `build_journal`
    takes.

    Note the hour bins key off a track's FIRST SIGHTING while the day rows key
    off `Threat.created_at`, so the two totals can differ by a track or two right
    at the period edges. That's the correct trade: `created_at` is insert time and
    a backfill/replay shifts it, which would smear the hour-of-day picture.
    """
    in_period = _date_range(start, end)
    hours = [HourBucket(hour=h) for h in range(24)]
    totals = AnalyticsTotals()
    type_totals = dict.fromkeys(TARGET_TYPES, 0)
    type_days = dict.fromkeys(TARGET_TYPES, 0)
    durations: dict[AlertDurationBucket, int] = dict.fromkeys(ALERT_DURATION_BUCKETS, 0)

    in_range = [s for s in day_stats if start.isoformat() <= s.date <= end.isoformat()]
    for s in in_range:
        totals.attacks += s.attack_count
        totals.tracks += s.track_count
        totals.targets += s.target_count
        totals.impacts += s.impact_count
        totals.alerts += s.alert_count
        totals.alert_seconds += s.alert_seconds
        totals.longest_alert_seconds = max(totals.longest_alert_seconds, s.longest_alert_seconds)
        totals.alert_incomplete |= s.alert_incomplete
        if _has_activity(s):
            totals.active_days += 1
        for target_type, count in s.type_counts.items():
            if count:
                type_totals[target_type] = type_totals.get(target_type, 0) + count
                type_days[target_type] = type_days.get(target_type, 0) + 1

    complete_seconds: list[int] = []
    for started_at, ended_at, closed_reason in alert_windows:
        if kyiv_date(started_at, tz) not in in_period:
            continue
        if ended_at is None or closed_reason == "failsafe":
            continue  # unknown duration — counted in totals.alerts, nowhere else
        seconds = int((naive(ended_at) - naive(started_at)).total_seconds())
        if seconds <= 0:
            continue
        complete_seconds.append(seconds)
        durations[duration_bucket(seconds)] += 1
        _spread_alert_minutes(started_at, ended_at, hours, tz)

    for event_time, weight in target_first_seen:
        local = kyiv_local(event_time, tz)
        if local.date() in in_period:
            hours[local.hour].target_count += weight or 1

    per_district: dict[int, DistrictStat] = {}
    district_days: dict[int, set[date]] = defaultdict(set)
    for event_time, district_id, is_impact in district_events:
        if district_id == sentinel_district_id:
            continue  # the citywide sentinel is not a place
        day = kyiv_date(event_time, tz)
        if day not in in_period:
            continue
        stat = per_district.setdefault(district_id, DistrictStat(district_id=district_id))
        stat.events += 1
        if is_impact:
            stat.impacts += 1
        district_days[district_id].add(day)
    for district_id, days_seen in district_days.items():
        per_district[district_id].days = len(days_seen)

    alert_days_observed = 0
    if alert_start is not None:
        coverage_start = max(alert_start, start)
        if coverage_start <= end:
            alert_days_observed = (end - coverage_start).days + 1
            _fill_quiet_streak(totals, in_range, coverage_start)

    for h in hours:
        if alert_days_observed:
            h.alert_share = h.alert_minutes / (alert_days_observed * 60)

    return AnalyticsStat(
        from_date=start.isoformat(),
        to_date=end.isoformat(),
        days_observed=(end - start).days + 1,
        alert_from_date=alert_start.isoformat() if alert_start is not None else None,
        alert_days_observed=alert_days_observed,
        totals=totals,
        hours=hours,
        type_totals=type_totals,
        type_days=type_days,
        alert_durations=durations,
        median_alert_seconds=int(median(complete_seconds)) if complete_seconds else 0,
        mean_alert_seconds=int(mean(complete_seconds)) if complete_seconds else 0,
        districts=sorted(
            per_district.values(), key=lambda d: (-d.days, -d.events, d.district_id)
        )[:top_districts],
    )


def _date_range(start: date, end: date) -> set[date]:
    days: set[date] = set()
    d = start
    while d <= end:
        days.add(d)
        d += timedelta(days=1)
    return days


def _fill_quiet_streak(totals: AnalyticsTotals, day_stats: list[DayStat], since: date) -> None:
    """Longest run of consecutive alert-free days, counted only over days the
    alert feed actually covered (before it existed, silence proves nothing)."""
    run = 0
    run_start: str | None = None
    for s in day_stats:
        if s.date < since.isoformat():
            continue
        if s.alert_count:
            run = 0
            run_start = None
            continue
        run += 1
        if run_start is None:
            run_start = s.date
        if run > totals.quiet_streak_days:
            totals.quiet_streak_days = run
            totals.quiet_streak_from = run_start
            totals.quiet_streak_to = s.date

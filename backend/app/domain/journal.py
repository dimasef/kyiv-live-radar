"""Per-day aggregation for the "Журнал повітряних загроз" page (GET /journal/days).

Pure and I/O-free: takes already-loaded ORM rows + a tzinfo, returns one
`DayStat` per calendar day in the requested range. The one real subtlety is the
timezone — stored datetimes are UTC wall-clock (SQLite drops tzinfo on
round-trip), but day boundaries must be **Europe/Kyiv**, so every timestamp is
bucketed by its Kyiv-local date. Data volume is tiny (single user, weeks of
data), so the caller fetches whole tables and this filters in Python — no
DB-specific date functions, no SQLite-vs-Postgres tz mismatch.

The intensity score is deliberately NOT computed here — the frontend owns the
weighting (single place to tweak) and derives it from these raw fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ..models import TARGET_TYPES
from ..timeutil import naive

KYIV = ZoneInfo("Europe/Kyiv")


def _kyiv_date(dt: datetime, tz: ZoneInfo) -> date:
    """Naive-UTC (or aware) datetime -> its calendar date in `tz`."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz).date()


@dataclass
class DayStat:
    date: str  # Kyiv-local ISO date, YYYY-MM-DD
    attack_count: int = 0  # incidents started this day
    track_count: int = 0  # inbound tracks (excludes impacts and citywide banners)
    target_count: int = 0  # sum of stated group sizes over those tracks
    impact_count: int = 0  # confirmed strikes
    type_counts: dict = field(default_factory=lambda: {t: 0 for t in TARGET_TYPES})
    alert_count: int = 0
    alert_seconds: int = 0  # Σ duration of complete city alerts
    longest_alert_seconds: int = 0
    # True when some alert this day was still open or failsafe-closed (its
    # duration is unknown/unreliable) — the UI marks the total as a lower bound.
    alert_incomplete: bool = False
    # Individual тривога→відбій windows (chronological): dicts of
    # {started_at, ended_at, seconds, incomplete} — the UI lists each interval
    # and highlights the longest. seconds stays 0 for incomplete windows so a
    # stuck failsafe alert can never win "longest".
    alert_windows: list = field(default_factory=list)
    district_ids: list = field(default_factory=list)
    district_count: int = 0


def build_journal(
    start: date,
    end: date,
    *,
    threats,
    incidents,
    alerts,
    district_events,
    sentinel_district_id: int | None = None,
    tz: ZoneInfo = KYIV,
) -> list[DayStat]:
    """Aggregate rows into one `DayStat` per day in [start, end] (inclusive).

    `district_events` is an iterable of `(event_time, district_id)` pairs.
    Rows outside the range are ignored (they bucket to a day not in the map).
    An alert spanning midnight is attributed entirely to its start day.
    """
    days: dict[date, DayStat] = {}
    d = start
    while d <= end:
        days[d] = DayStat(date=d.isoformat())
        d += timedelta(days=1)

    def bucket(dt: datetime) -> DayStat | None:
        return days.get(_kyiv_date(dt, tz))

    for inc in incidents:
        s = bucket(inc.started_at)
        if s is not None:
            s.attack_count += 1

    for th in threats:
        s = bucket(th.created_at)
        if s is None:
            continue
        if th.scope == "city":
            # A citywide banner is not a discrete target — keep it out of the
            # track/target/type tallies (it would otherwise inflate every count).
            continue
        tt = th.target_type if th.target_type in s.type_counts else "unknown"
        s.type_counts[tt] += 1
        if th.status == "impact" or th.kind == "impact":
            s.impact_count += 1
        else:
            s.track_count += 1
            s.target_count += th.target_count or 1

    districts_per_day: dict[date, dict[int, int]] = {}
    for event_time, district_id in district_events:
        if district_id == sentinel_district_id:
            continue
        key = _kyiv_date(event_time, tz)
        if key not in days:
            continue
        counts = districts_per_day.setdefault(key, {})
        counts[district_id] = counts.get(district_id, 0) + 1
    for key, counts in districts_per_day.items():
        s = days[key]
        # Most-active first, so the UI's "top districts" is meaningful (id
        # tiebreak keeps the order deterministic).
        s.district_ids = sorted(counts, key=lambda i: (-counts[i], i))
        s.district_count = len(counts)

    for a in alerts:
        if a.scope != "city":
            continue
        s = bucket(a.started_at)
        if s is None:
            continue
        s.alert_count += 1
        incomplete = a.ended_at is None or a.closed_reason == "failsafe"
        window = {
            "started_at": naive(a.started_at),
            "ended_at": naive(a.ended_at) if a.ended_at is not None else None,
            "seconds": 0,
            "incomplete": incomplete,
        }
        if incomplete:
            s.alert_incomplete = True
        else:
            dur = int((naive(a.ended_at) - naive(a.started_at)).total_seconds())
            if dur < 0:
                dur = 0
            window["seconds"] = dur
            s.alert_seconds += dur
            s.longest_alert_seconds = max(s.longest_alert_seconds, dur)
        s.alert_windows.append(window)

    for s in days.values():
        s.alert_windows.sort(key=lambda w: w["started_at"])

    return [days[k] for k in sorted(days)]

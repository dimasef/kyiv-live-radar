"""Journal aggregation: the per-day calendar (GET /journal/days) and the
across-days statistics tab (GET /journal/stats)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_session
from ...domain.analytics import build_analytics
from ...domain.districts import citywide_district_id
from ...domain.journal import KYIV, build_journal
from ...models import (
    ANALYTICS_PERIODS,
    Alert,
    Incident,
    Threat,
    ThreatEvent,
)
from ...schemas import (
    DistrictStatOut,
    DurationBucketOut,
    HourBucketOut,
    JournalOut,
    JournalStatsOut,
    StatsDayOut,
    StatsTotalsOut,
)
from ...timeutil import kyiv_date
from ..serialize import journal_out as _journal_out

router = APIRouter()

# How far back each period preset reaches; 'all' is resolved from the data.
_PERIOD_DAYS: dict[str, int] = {"30d": 29, "90d": 89}


@dataclass
class _Window:
    """Everything build_journal needs for one Kyiv-local day range."""

    threats: list
    incidents: list
    alerts: list
    district_events: list
    sentinel: int | None
    hide_impacts_from: date | None
    # The padded naive-UTC bounds the rows were loaded with, so a caller can run
    # its own extra query over exactly the same window.
    window_start: datetime
    window_end: datetime


async def _load_window(session: AsyncSession, start: date, end: date, today: date) -> _Window:
    """Load the rows that could bucket into [start, end].

    Naive-UTC bounds for the requested Kyiv-local range. A day's worth of padding
    on each side absorbs the UTC+2/+3 offset with room to spare, so build_journal
    still sees every row that could bucket into [start, end] — it drops anything
    outside the range itself. Without this the endpoint read whole tables on
    every calendar load.
    """
    window_start = datetime.combine(start, time.min) - timedelta(days=1)
    window_end = datetime.combine(end, time.min) + timedelta(days=2)

    threats = list(
        await session.scalars(
            select(Threat).where(
                Threat.created_at >= window_start, Threat.created_at < window_end
            )
        )
    )
    incidents = list(
        await session.scalars(
            select(Incident).where(
                Incident.started_at >= window_start, Incident.started_at < window_end
            )
        )
    )
    alerts = list(
        await session.scalars(
            select(Alert).where(
                Alert.scope == "city",
                Alert.started_at >= window_start,
                Alert.started_at < window_end,
            )
        )
    )
    district_events = (
        await session.execute(
            select(
                ThreatEvent.event_time,
                ThreatEvent.district_id,
                Threat.kind == "impact",
            )
            .join(Threat, ThreatEvent.threat_id == Threat.id)
            .where(
                Threat.closed_reason.is_distinct_from("dismissed"),
                ThreatEvent.event_time >= window_start,
                ThreatEvent.event_time < window_end,
            )
        )
    ).all()
    sentinel = await citywide_district_id(session)
    # Where a strike landed is history, not live situational awareness: while
    # the city alert is still on, today's impacts stay out of the journal too
    # (they're already off the map, the feed and the banner). They appear on
    # the next load once the відбій lands.
    alert_open = await session.scalar(
        select(Alert.id).where(Alert.scope == "city", Alert.ended_at.is_(None))
    )
    return _Window(
        threats=threats,
        incidents=incidents,
        alerts=alerts,
        district_events=district_events,
        sentinel=sentinel,
        hide_impacts_from=today if alert_open is not None else None,
        window_start=window_start,
        window_end=window_end,
    )


@router.get("/journal/days", response_model=JournalOut)
async def journal_days(
    from_: str | None = Query(None, alias="from", description="Start day (Kyiv), YYYY-MM-DD"),
    to: str | None = Query(None, description="End day (Kyiv), YYYY-MM-DD; defaults to today"),
    session: AsyncSession = Depends(get_session),
):
    """Per-day threat activity for the journal calendar: attacks, targets,
    target-type mix, alert duration and districts touched, one row per day in
    [from, to] inclusive (zero-activity days included). Days are bucketed by
    Europe/Kyiv local date. The SQL only bounds the range; all bucketing happens
    in Python (see domain/journal.py) — no tz-fragile SQL date math."""
    today = datetime.now(UTC).astimezone(KYIV).date()
    try:
        end = date.fromisoformat(to) if to else today
        start = date.fromisoformat(from_) if from_ else end - timedelta(days=34)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date (expected YYYY-MM-DD)") from None
    if start > end:
        raise HTTPException(status_code=400, detail="'from' must be on or before 'to'")
    if (end - start).days > 92:
        raise HTTPException(status_code=400, detail="Range too large (max 92 days)")

    w = await _load_window(session, start, end, today)
    stats = build_journal(
        start,
        end,
        threats=w.threats,
        incidents=w.incidents,
        alerts=w.alerts,
        district_events=w.district_events,
        sentinel_district_id=w.sentinel,
        hide_impacts_from=w.hide_impacts_from,
    )
    return JournalOut(
        from_date=start.isoformat(),
        to_date=end.isoformat(),
        days=[_journal_out(s) for s in stats],
    )


@router.get("/journal/stats", response_model=JournalStatsOut)
async def journal_stats(
    period: str = Query("30d", description=f"One of {', '.join(ANALYTICS_PERIODS)}"),
    session: AsyncSession = Depends(get_session),
):
    """Across-days statistics for the journal's «Статистика» tab: period totals,
    hour-of-day distribution of alerts and targets, per-day rows for the trend
    chart, alert-duration histogram and the most-affected districts.

    Deliberately a separate route from /journal/days: 'all' is uncapped, and the
    payload is a different aggregation shape (across days, not per day)."""
    if period not in ANALYTICS_PERIODS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid period (expected one of {', '.join(ANALYTICS_PERIODS)})",
        )
    today = datetime.now(UTC).astimezone(KYIV).date()
    end = today
    if period == "all":
        start = await _first_data_day(session) or end
    else:
        start = end - timedelta(days=_PERIOD_DAYS[period])

    w = await _load_window(session, start, end, today)
    day_stats = build_journal(
        start,
        end,
        threats=w.threats,
        incidents=w.incidents,
        alerts=w.alerts,
        district_events=w.district_events,
        sentinel_district_id=w.sentinel,
        hide_impacts_from=w.hide_impacts_from,
    )
    # Targets are binned by their FIRST SIGHTING, not Threat.created_at (insert
    # time — a backfill/replay shifts it and would smear the hour-of-day picture).
    first_seen = (
        await session.execute(
            select(func.min(ThreatEvent.event_time), Threat.target_count)
            .join(Threat, ThreatEvent.threat_id == Threat.id)
            .where(
                Threat.closed_reason.is_distinct_from("dismissed"),
                Threat.kind != "impact",
                Threat.scope != "city",
                ThreatEvent.event_time >= w.window_start,
                ThreatEvent.event_time < w.window_end,
            )
            .group_by(Threat.id)
        )
    ).all()
    # The alert feed was added later than the spotter feed: every alert rate is
    # normalized on its own coverage window, not on the whole data range.
    alert_start = await session.scalar(
        select(func.min(Alert.started_at)).where(Alert.scope == "city")
    )

    stat = build_analytics(
        start,
        end,
        day_stats=day_stats,
        alert_windows=[
            (a.started_at, a.ended_at, a.closed_reason)
            for a in w.alerts
            if a.closed_reason != "dismissed"
        ],
        target_first_seen=first_seen,
        district_events=w.district_events,
        alert_start=kyiv_date(alert_start) if alert_start is not None else None,
        sentinel_district_id=w.sentinel,
    )
    return JournalStatsOut(
        period=period,
        from_date=stat.from_date,
        to_date=stat.to_date,
        days_observed=stat.days_observed,
        alert_from_date=stat.alert_from_date,
        alert_days_observed=stat.alert_days_observed,
        totals=StatsTotalsOut(**vars(stat.totals)),
        days=[
            StatsDayOut(
                date=s.date,
                attack_count=s.attack_count,
                track_count=s.track_count,
                target_count=s.target_count,
                impact_count=s.impact_count,
                alert_count=s.alert_count,
                alert_seconds=s.alert_seconds,
                alert_incomplete=s.alert_incomplete,
                type_counts=s.type_counts,
            )
            for s in day_stats
        ],
        hours=[HourBucketOut(**vars(h)) for h in stat.hours],
        type_totals=stat.type_totals,
        type_days=stat.type_days,
        alert_durations=[
            DurationBucketOut(bucket=bucket, count=count)
            for bucket, count in stat.alert_durations.items()
        ],
        median_alert_seconds=stat.median_alert_seconds,
        mean_alert_seconds=stat.mean_alert_seconds,
        districts=[DistrictStatOut(**vars(d)) for d in stat.districts],
    )


async def _first_data_day(session: AsyncSession) -> date | None:
    """The earliest Kyiv day with any activity at all — the 'all time' start."""
    firsts = [
        await session.scalar(select(func.min(Threat.created_at))),
        await session.scalar(select(func.min(Incident.started_at))),
        await session.scalar(select(func.min(Alert.started_at))),
    ]
    known = [dt for dt in firsts if dt is not None]
    return min(kyiv_date(dt) for dt in known) if known else None

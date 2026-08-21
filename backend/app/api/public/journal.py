"""Journal aggregation: the per-day calendar (GET /journal/days) and the
across-days statistics tab (GET /journal/stats)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_session
from ...domain.analytics import build_analytics
from ...domain.journal import KYIV, build_journal
from ...models import (
    ANALYTICS_PERIODS,
    HOME_REGION,
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
from ..journal_window import load_journal_window
from ..serialize import journal_out as _journal_out

router = APIRouter()

# How far back each period preset reaches; 'all' is resolved from the data.
_PERIOD_DAYS: dict[str, int] = {"30d": 29, "90d": 89}


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

    w = await load_journal_window(session, start, end, today)
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

    w = await load_journal_window(session, start, end, today)
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
                Threat.region == HOME_REGION,
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
    """The earliest Kyiv day with any activity at all — the 'all time' start.

    Scoped exactly like the journal itself (Kyiv tracks, city alerts): an
    oblast-scope alert or a northern track must not stretch the range back to a
    day the statistics then render as empty."""
    firsts = [
        await session.scalar(
            select(func.min(Threat.created_at)).where(Threat.region == HOME_REGION)
        ),
        await session.scalar(select(func.min(Incident.started_at))),
        await session.scalar(
            select(func.min(Alert.started_at)).where(Alert.scope == "city")
        ),
    ]
    known = [dt for dt in firsts if dt is not None]
    return min(kyiv_date(dt) for dt in known) if known else None

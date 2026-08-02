"""Per-day threat-activity aggregation for the journal calendar (GET /journal/days)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_session
from ...domain.districts import citywide_district_id
from ...domain.journal import KYIV, build_journal
from ...models import (
    Alert,
    Incident,
    Threat,
    ThreatEvent,
)
from ...schemas import (
    JournalOut,
)
from ..serialize import journal_out as _journal_out

router = APIRouter()


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

    # Naive-UTC bounds for the requested Kyiv-local range. A day's worth of
    # padding on each side absorbs the UTC+2/+3 offset with room to spare, so
    # build_journal still sees every row that could bucket into [start, end] —
    # it drops anything outside the range itself. Without this the endpoint read
    # whole tables on every calendar load.
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

    stats = build_journal(
        start,
        end,
        threats=threats,
        incidents=incidents,
        alerts=alerts,
        district_events=district_events,
        sentinel_district_id=sentinel,
        hide_impacts_from=today if alert_open is not None else None,
    )
    return JournalOut(
        from_date=start.isoformat(),
        to_date=end.isoformat(),
        days=[_journal_out(s) for s in stats],
    )

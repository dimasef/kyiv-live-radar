"""Loading the rows a Kyiv-local day range can bucket into.

Shared by the journal endpoints and the admin reprocess preview, which reports
the same per-day counts and must therefore read the same window — before this
was shared it read whole tables instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.districts import citywide_district_id
from ..models import (
    HOME_REGION,
    Alert,
    District,
    Incident,
    Threat,
    ThreatEvent,
)


@dataclass
class JournalWindow:
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


async def load_journal_window(
    session: AsyncSession, start: date, end: date, today: date
) -> JournalWindow:
    """Load the rows that could bucket into [start, end].

    Naive-UTC bounds for the requested Kyiv-local range. A day's worth of padding
    on each side absorbs the UTC+2/+3 offset with room to spare, so build_journal
    still sees every row that could bucket into [start, end] — it drops anything
    outside the range itself. Without this the endpoint read whole tables on
    every calendar load.

    The journal is about KYIV. Northern early-warning tracks and the districts
    they pass over are watched to see what is coming, not to be counted as
    nights this city lived through — so both the threat rows and the district
    histogram are filtered to HOME_REGION here rather than in build_journal,
    which stays a pure function over whatever it is handed.
    """
    window_start = datetime.combine(start, time.min) - timedelta(days=1)
    window_end = datetime.combine(end, time.min) + timedelta(days=2)

    threats = list(
        await session.scalars(
            select(Threat).where(
                Threat.region == HOME_REGION,
                Threat.created_at >= window_start,
                Threat.created_at < window_end,
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
            .join(District, ThreatEvent.district_id == District.id)
            .where(
                Threat.closed_reason.is_distinct_from("dismissed"),
                Threat.region == HOME_REGION,
                District.region == HOME_REGION,
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
    return JournalWindow(
        threats=threats,
        incidents=incidents,
        alerts=alerts,
        district_events=district_events,
        sentinel=sentinel,
        hide_impacts_from=today if alert_open is not None else None,
        window_start=window_start,
        window_end=window_end,
    )

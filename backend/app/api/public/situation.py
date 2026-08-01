"""The live layers around the tracks themselves: feed notices, official air-raid
alerts, grouped incidents (attacks) and directional threat axes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...db import get_session
from ...domain.districts import citywide_district_id
from ...models import (
    Alert,
    Incident,
    Notice,
    Threat,
    ThreatAxis,
)
from ...schemas import (
    AlertOut,
    AxisOut,
    IncidentOut,
    NoticeOut,
)
from ..serialize import alert_out as _alert_out
from ..serialize import axis_out as _axis_out
from ..serialize import incident_out as _incident_out
from ..serialize import notice_out as _notice_out

router = APIRouter()


@router.get("/notices/recent", response_model=list[NoticeOut])
async def recent_notices(
    limit: int = Query(30, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """Recent non-threat notices (all-clears / attack summaries), newest first —
    the frontend interleaves them into the event feed as info entries."""
    stmt = (
        select(Notice)
        .options(selectinload(Notice.source))
        .order_by(Notice.event_time.desc(), Notice.id.desc())
        .limit(limit)
    )
    return [_notice_out(n) for n in await session.scalars(stmt)]


@router.get("/alerts/active", response_model=list[AlertOut])
async def active_alerts(session: AsyncSession = Depends(get_session)):
    """Currently open official alert windows (usually 0 or 1 per scope —
    city and oblast can be open independently)."""
    stmt = select(Alert).where(Alert.ended_at.is_(None)).order_by(Alert.started_at.desc())
    return [_alert_out(a) for a in await session.scalars(stmt)]


@router.get("/alerts/recent", response_model=list[AlertOut])
async def recent_alerts(
    limit: int = Query(30, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Alert).order_by(Alert.started_at.desc()).limit(limit)
    return [_alert_out(a) for a in await session.scalars(stmt)]


@router.get("/incidents/active", response_model=list[IncidentOut])
async def active_incidents(session: AsyncSession = Depends(get_session)):
    """Ongoing attacks (incidents not yet ended), each with counts aggregated
    over its member threats — the "one attack" rollup for the UI summary strip."""
    sentinel_id = await citywide_district_id(session)
    stmt = (
        select(Incident)
        .where(Incident.ended_at.is_(None))
        .options(
            selectinload(Incident.threats).selectinload(Threat.events),
        )
        .order_by(Incident.started_at.desc())
    )
    incidents = await session.scalars(stmt)
    return [_incident_out(inc, sentinel_id) for inc in incidents]


@router.get("/incidents/recent", response_model=list[IncidentOut])
async def recent_incidents(
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """Most recent attacks (ended or active), newest first — hydrates the feed's
    attack-summary cards on load so an incident that ended before the client
    connected still renders its rollup."""
    sentinel_id = await citywide_district_id(session)
    stmt = (
        select(Incident)
        # Admin-dismissed attacks are false positives — never hydrate a summary
        # card for them (the live WS path already drops them; this is the reload
        # counterpart). is_distinct_from keeps active incidents (ended_reason NULL).
        .where(Incident.ended_reason.is_distinct_from("dismissed"))
        .options(selectinload(Incident.threats).selectinload(Threat.events))
        .order_by(Incident.started_at.desc())
        .limit(limit)
    )
    incidents = await session.scalars(stmt)
    return [_incident_out(inc, sentinel_id) for inc in incidents]


@router.get("/axes/active", response_model=list[AxisOut])
async def active_axes(session: AsyncSession = Depends(get_session)):
    """Live directional threat axes (not yet expired), newest first — the map's
    screen-edge wedge layer. Supplementary, volunteer-sourced; never the alert."""
    stmt = (
        select(ThreatAxis)
        .where(ThreatAxis.expires_at.is_(None))
        .order_by(ThreatAxis.created_at.desc())
    )
    return [_axis_out(a) for a in await session.scalars(stmt)]

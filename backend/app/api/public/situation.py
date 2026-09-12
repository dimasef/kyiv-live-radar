"""The live layers around the tracks themselves: feed notices, official air-raid
alerts, grouped incidents (attacks) and directional threat axes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import TypeAdapter
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
from ...realtime.serialize import alert_out as _alert_out
from ...realtime.serialize import axis_out as _axis_out
from ...realtime.serialize import incident_out as _incident_out
from ...realtime.serialize import notice_out as _notice_out
from ...schemas import (
    AlertOut,
    AxisOut,
    IncidentOut,
    NoticeOut,
)
from ..read_cache import cached_json

router = APIRouter()

_NOTICES = TypeAdapter(list[NoticeOut])
_ALERTS = TypeAdapter(list[AlertOut])
_INCIDENTS = TypeAdapter(list[IncidentOut])
_AXES = TypeAdapter(list[AxisOut])


@router.get("/notices/recent", response_model=list[NoticeOut])
async def recent_notices(
    limit: int = Query(30, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """Recent non-threat notices (all-clears / attack summaries), newest first —
    the frontend interleaves them into the event feed as info entries."""
    return await cached_json(notices_key(limit), lambda: render_recent_notices(session, limit))


def notices_key(limit: int) -> str:
    return f"notices:{limit}"


async def render_recent_notices(session: AsyncSession, limit: int) -> bytes:
    stmt = (
        select(Notice)
        .options(selectinload(Notice.source))
        .order_by(Notice.event_time.desc(), Notice.id.desc())
        .limit(limit)
    )
    return _NOTICES.dump_json([_notice_out(n) for n in await session.scalars(stmt)])


@router.get("/alerts/active", response_model=list[AlertOut])
async def active_alerts(session: AsyncSession = Depends(get_session)):
    """Currently open official alert windows (usually 0 or 1 per scope —
    city and oblast can be open independently)."""
    return await cached_json("alerts:active", lambda: render_active_alerts(session))


async def render_active_alerts(session: AsyncSession) -> bytes:
    stmt = select(Alert).where(Alert.ended_at.is_(None)).order_by(Alert.started_at.desc())
    return _ALERTS.dump_json([_alert_out(a) for a in await session.scalars(stmt)])


@router.get("/alerts/recent", response_model=list[AlertOut])
async def recent_alerts(
    limit: int = Query(30, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    return await cached_json(alerts_key(limit), lambda: render_recent_alerts(session, limit))


def alerts_key(limit: int) -> str:
    return f"alerts:{limit}"


async def render_recent_alerts(session: AsyncSession, limit: int) -> bytes:
    stmt = select(Alert).order_by(Alert.started_at.desc()).limit(limit)
    return _ALERTS.dump_json([_alert_out(a) for a in await session.scalars(stmt)])


@router.get("/incidents/active", response_model=list[IncidentOut])
async def active_incidents(session: AsyncSession = Depends(get_session)):
    """Ongoing attacks (incidents not yet ended), each with counts aggregated
    over its member threats — the "one attack" rollup for the UI summary strip."""
    return await cached_json(INCIDENTS_ACTIVE, lambda: render_active_incidents(session))


INCIDENTS_ACTIVE = "incidents:active"


async def render_active_incidents(session: AsyncSession) -> bytes:
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
    return _INCIDENTS.dump_json([_incident_out(inc, sentinel_id) for inc in incidents])


@router.get("/incidents/recent", response_model=list[IncidentOut])
async def recent_incidents(
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """Most recent attacks (ended or active), newest first — hydrates the feed's
    attack-summary cards on load so an incident that ended before the client
    connected still renders its rollup."""
    return await cached_json(
        incidents_key(limit), lambda: render_recent_incidents(session, limit)
    )


def incidents_key(limit: int) -> str:
    return f"incidents:{limit}"


async def render_recent_incidents(session: AsyncSession, limit: int) -> bytes:
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
    return _INCIDENTS.dump_json([_incident_out(inc, sentinel_id) for inc in incidents])


@router.get("/axes/active", response_model=list[AxisOut])
async def active_axes(session: AsyncSession = Depends(get_session)):
    """Live directional threat axes (not yet expired), newest first — the map's
    screen-edge wedge layer. Supplementary, volunteer-sourced; never the alert."""
    return await cached_json(AXES_ACTIVE, lambda: render_active_axes(session))


AXES_ACTIVE = "axes:active"


async def render_active_axes(session: AsyncSession) -> bytes:
    stmt = (
        select(ThreatAxis)
        .where(ThreatAxis.expires_at.is_(None))
        .order_by(ThreatAxis.created_at.desc())
    )
    return _AXES.dump_json([_axis_out(a) for a in await session.scalars(stmt)])

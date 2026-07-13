from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import settings
from ..db import get_session
from ..domain.districts import citywide_district_id
from ..models import Alert, District, Incident, Notice, Threat, ThreatEvent, utcnow
from ..schemas import (
    AlertOut,
    DistrictOut,
    FeedEntryOut,
    IncidentOut,
    NoticeOut,
    ThreatEventOut,
    ThreatOut,
)
from ..timeutil import within
from .serialize import alert_out as _alert_out
from .serialize import event_out as _event_out
from .serialize import feed_entry_out as _feed_entry_out
from .serialize import incident_out as _incident_out
from .serialize import notice_out as _notice_out
from .serialize import threat_out as _threat_out

router = APIRouter()


@router.get("/districts", response_model=list[DistrictOut])
async def list_districts(session: AsyncSession = Depends(get_session)):
    rows = await session.scalars(select(District).order_by(District.name_en))
    return list(rows)


@router.get("/districts/boundaries")
async def district_boundaries(session: AsyncSession = Depends(get_session)):
    """Real OSM boundary polygons for districts that have one (the 10 raions)."""
    rows = await session.scalars(
        select(District).where(District.boundary.is_not(None)).order_by(District.name_en)
    )
    return [
        {"id": d.id, "name_uk": d.name_uk, "name_en": d.name_en, "geojson": d.boundary}
        for d in rows
    ]


@router.get("/threats/active", response_model=list[ThreatOut])
async def active_threats(session: AsyncSession = Depends(get_session)):
    """Tracks that are not yet closed (still tracking / unconfirmed), plus
    RECENT `impact` markers — those are closed-on-creation (a strike is terminal)
    but persist on the map as confirmed-hit pins. Only impacts within
    `impact_map_ttl_hours` are returned, so strikes from days-old attacks don't
    accumulate on the live map (history/feed keep them regardless)."""
    stmt = (
        select(Threat)
        .where(or_(Threat.closed_at.is_(None), Threat.status == "impact"))
        .options(
            selectinload(Threat.events).selectinload(ThreatEvent.district),
            selectinload(Threat.events).selectinload(ThreatEvent.source),
        )
        .order_by(Threat.created_at.desc())
    )
    ttl = timedelta(hours=settings.impact_map_ttl_hours)
    now = utcnow()
    out = []
    for t in await session.scalars(stmt):
        # Drop stale impact pins; live inbound tracks (closed_at IS NULL) always pass.
        if t.status == "impact" and t.closed_at is not None and not within(t.closed_at, now, ttl):
            continue
        out.append(_threat_out(t))
    return out


@router.get("/events/recent", response_model=list[FeedEntryOut])
async def recent_events(
    limit: int = Query(60, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    """Most recent sightings across ALL tracks (open or closed), newest first —
    hydrates the frontend event feed on page load (it otherwise only grows from
    live WebSocket traffic and empties on every reload)."""
    stmt = (
        select(ThreatEvent)
        .options(
            selectinload(ThreatEvent.district),
            selectinload(ThreatEvent.source),
            selectinload(ThreatEvent.threat),
        )
        # Secondary key so events sharing an event_time (e.g. one "дорозвідка"
        # message closing several tracks at once) sort deterministically and
        # stay adjacent — plain event_time ties have undefined order otherwise,
        # which would scatter a group the frontend expects to find contiguous.
        .order_by(ThreatEvent.event_time.desc(), ThreatEvent.id.desc())
        .limit(limit)
    )
    events = await session.scalars(stmt)
    return [_feed_entry_out(ev) for ev in events]


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


@router.get("/threats/{threat_id}/events", response_model=list[ThreatEventOut])
async def threat_events(threat_id: int, session: AsyncSession = Depends(get_session)):
    stmt = (
        select(ThreatEvent)
        .where(ThreatEvent.threat_id == threat_id)
        .options(
            selectinload(ThreatEvent.district),
            selectinload(ThreatEvent.source),
        )
        .order_by(ThreatEvent.event_time)
    )
    events = list(await session.scalars(stmt))
    if not events:
        # Distinguish "no such threat" from "threat with no events".
        exists = await session.get(Threat, threat_id)
        if exists is None:
            raise HTTPException(status_code=404, detail="threat not found")
    return [_event_out(ev) for ev in events]

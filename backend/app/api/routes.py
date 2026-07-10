from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db import get_session
from ..models import District, Threat, ThreatEvent
from ..schemas import DistrictOut, FeedEntryOut, ThreatEventOut, ThreatOut
from ..serialize import event_out as _event_out
from ..serialize import feed_entry_out as _feed_entry_out
from ..serialize import threat_out as _threat_out

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
    """Tracks that are not yet closed (still tracking / unconfirmed)."""
    stmt = (
        select(Threat)
        .where(Threat.closed_at.is_(None))
        .options(
            selectinload(Threat.events).selectinload(ThreatEvent.district),
            selectinload(Threat.events).selectinload(ThreatEvent.source),
        )
        .order_by(Threat.created_at.desc())
    )
    threats = await session.scalars(stmt)
    return [_threat_out(t) for t in threats]


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

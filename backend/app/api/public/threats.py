"""Live threat tracks and the event feed — the map's and the log's primary reads."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...config import settings
from ...db import get_session
from ...models import (
    Threat,
    ThreatEvent,
    utcnow,
)
from ...schemas import (
    FeedEntryOut,
    ThreatEventOut,
    ThreatOut,
)
from ...timeutil import within
from ..serialize import event_out as _event_out
from ..serialize import feed_entry_out as _feed_entry_out
from ..serialize import threat_out as _threat_out

router = APIRouter()


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
        # Hide events of admin-dismissed tracks (is_distinct_from so open tracks,
        # whose closed_reason is NULL, still pass — a plain != would drop them).
        .join(Threat, ThreatEvent.threat_id == Threat.id)
        .where(Threat.closed_reason.is_distinct_from("dismissed"))
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

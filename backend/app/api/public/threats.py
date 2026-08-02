"""Live threat tracks and the event feed — the map's and the log's primary reads."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...db import get_session
from ...models import (
    Threat,
    ThreatEvent,
)
from ...schemas import (
    FeedEntryOut,
    ThreatEventOut,
    ThreatOut,
)
from ..serialize import event_out as _event_out
from ..serialize import feed_entry_out as _feed_entry_out
from ..serialize import threat_out as _threat_out

router = APIRouter()


@router.get("/threats/active", response_model=list[ThreatOut])
async def active_threats(session: AsyncSession = Depends(get_session)):
    """Tracks that are not yet closed (still tracking / unconfirmed).

    Impact markers are deliberately NOT here even though they carry a location:
    publishing where a strike landed, while the attack is still running, is
    battle-damage assessment for whoever launched it. They stay in the DB and
    surface only in the journal, once the alert is over (see
    api/public/journal.py) — the same reason `incident_out` never publishes an
    impact count and `broadcast.py` never fans one out.
    """
    stmt = (
        select(Threat)
        .where(Threat.closed_at.is_(None))
        .options(
            selectinload(Threat.events).selectinload(ThreatEvent.district),
            selectinload(Threat.events).selectinload(ThreatEvent.source),
        )
        .order_by(Threat.created_at.desc())
    )
    return [_threat_out(t) for t in await session.scalars(stmt)]


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
        # Impact events are hidden for the same reason they're off the map: a
        # live "hit in Дарницький" card is damage assessment for the attacker.
        .join(Threat, ThreatEvent.threat_id == Threat.id)
        .where(
            Threat.closed_reason.is_distinct_from("dismissed"),
            Threat.kind.is_distinct_from("impact"),
        )
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
    threat = await session.get(Threat, threat_id)
    if threat is None:
        raise HTTPException(status_code=404, detail="threat not found")
    # An impact's district is withheld everywhere else (see active_threats) —
    # this route must not become the hole that hands it out by id.
    if threat.kind == "impact":
        raise HTTPException(status_code=404, detail="threat not found")
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
    return [_event_out(ev) for ev in events]

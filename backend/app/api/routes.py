from __future__ import annotations

from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import settings
from ..db import get_session
from ..domain.districts import citywide_district_id
from ..domain.home_danger import raion_ids_for_zone
from ..models import (
    Alert,
    District,
    Incident,
    Notice,
    PushSubscription,
    RawMessage,
    Source,
    Threat,
    ThreatAxis,
    ThreatEvent,
    utcnow,
)
from ..schemas import (
    AlertOut,
    AxisOut,
    DistrictOut,
    FeedEntryOut,
    IncidentOut,
    NoticeOut,
    PushConfigOut,
    PushSubscribeIn,
    PushUnsubscribeIn,
    RawCountOut,
    RawExportOut,
    RawLlmStatsOut,
    RawMessagesPage,
    RawSourceOut,
    ThreatEventOut,
    ThreatOut,
)
from ..timeutil import within
from .raw_query import apply_raw_filters, serialize_raw_rows
from .serialize import alert_out as _alert_out
from .serialize import axis_out as _axis_out
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


@router.get("/raw_messages", response_model=RawMessagesPage)
async def raw_messages(
    limit: int = Query(50, ge=1, le=200),
    before_id: Optional[int] = Query(None, description="Return rows with id < this (cursor)"),
    q: Optional[str] = Query(
        None,
        description="Substring search over message text, OR one/more T{id}/M{id}/N{id} "
        "codes (the same dev badges shown in the feed) to look up by exact match instead",
    ),
    outcome: Optional[str] = Query(
        None, description="'event' = became a sighting or notice; 'suppressed' = everything else"
    ),
    llm: Optional[str] = Query(
        None, description="'yes'|'no' — whether the LLM fallback was called (NULL rows excluded)"
    ),
    source_id: Optional[int] = Query(None, description="Filter to one monitored channel"),
    session: AsyncSession = Depends(get_session),
):
    """Every ingested message verbatim, INCLUDING ones the parser suppressed
    or couldn't localize — a debug view onto the pipeline, distinct from
    /events/recent (which only shows messages that became a live sighting).
    Cursor-paginated (before_id) newest-first — raw_messages can run to tens
    of thousands of rows, too many to offset-paginate cheaply."""
    stmt = (
        select(RawMessage)
        .options(selectinload(RawMessage.source))
        .order_by(RawMessage.id.desc())
        .limit(limit)
    )
    if before_id is not None:
        stmt = stmt.where(RawMessage.id < before_id)
    stmt = apply_raw_filters(stmt, q=q, outcome=outcome, llm=llm, source_id=source_id)
    rows = list(await session.scalars(stmt))
    items = await serialize_raw_rows(session, rows)
    next_before_id = rows[-1].id if len(rows) == limit else None
    return RawMessagesPage(items=items, next_before_id=next_before_id)


@router.get("/raw_messages/count", response_model=RawCountOut)
async def raw_messages_count(
    q: Optional[str] = Query(None),
    outcome: Optional[str] = Query(None),
    llm: Optional[str] = Query(None),
    source_id: Optional[int] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """How many raw messages match the current filter set — powers the
    "показано N з M" counter on /raw without paging through everything."""
    stmt = apply_raw_filters(
        select(func.count()).select_from(RawMessage),
        q=q, outcome=outcome, llm=llm, source_id=source_id,
    )
    total = await session.scalar(stmt)
    return RawCountOut(count=total or 0)


# Guard rail: a filtered export of the whole corpus could be tens of thousands
# of rows. Cap it and flag truncation so a partial export never reads as
# complete. Keeps the MOST RECENT matches when it bites (see ordering below).
_RAW_EXPORT_CAP = 5000


@router.get("/raw_messages/export", response_model=RawExportOut)
async def raw_messages_export(
    q: Optional[str] = Query(None),
    outcome: Optional[str] = Query(None),
    llm: Optional[str] = Query(None),
    source_id: Optional[int] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """Every message matching the current filter (up to _RAW_EXPORT_CAP), for
    offline analysis. Returned oldest-first so the export reads as a sequence
    of events; the frontend wraps these in a JSON envelope with the human
    filter description before download."""
    stmt = (
        select(RawMessage)
        .options(selectinload(RawMessage.source))
        .order_by(RawMessage.id.desc())
        .limit(_RAW_EXPORT_CAP)
    )
    stmt = apply_raw_filters(stmt, q=q, outcome=outcome, llm=llm, source_id=source_id)
    rows = list(await session.scalars(stmt))
    truncated = len(rows) == _RAW_EXPORT_CAP
    rows.reverse()  # newest-first fetch (so truncation keeps recent) -> chronological output
    items = await serialize_raw_rows(session, rows)
    return RawExportOut(messages=items, truncated=truncated)


@router.get("/raw_messages/sources", response_model=list[RawSourceOut])
async def raw_messages_sources(session: AsyncSession = Depends(get_session)):
    """Currently-configured channels only, for the /raw channel filter
    dropdown — `sources` accumulates one row per channel_key ever resolved,
    including ones dropped from TELEGRAM_CHANNELS/ALERT_CHANNELS long ago
    (a channel migrating username leaves its old key behind), so it's NOT
    the same as "channels we actually watch today"."""
    configured = {
        c.lower() for c in settings.telegram_channel_list + settings.alert_channel_list
    }
    rows = await session.scalars(select(Source).order_by(Source.name))
    return [
        RawSourceOut(id=s.id, name=s.name) for s in rows if s.channel_key.lower() in configured
    ]


@router.get("/raw_messages/llm_stats", response_model=RawLlmStatsOut)
async def raw_messages_llm_stats(session: AsyncSession = Depends(get_session)):
    """Aggregate LLM fallback usage across ALL raw messages — total calls,
    tokens, and cost, for the analytics strip on /raw. Unfiltered (ignores
    search/outcome filters) so it always reads as "overall spend", not
    "spend within the current view"."""
    row = (
        await session.execute(
            select(
                func.count(RawMessage.id),
                func.coalesce(func.sum(RawMessage.llm_input_tokens), 0),
                func.coalesce(func.sum(RawMessage.llm_output_tokens), 0),
                func.coalesce(func.sum(RawMessage.llm_cost_usd), 0.0),
            ).where(RawMessage.llm_attempted.is_(True))
        )
    ).one()
    calls, input_tokens, output_tokens, cost_usd = row
    return RawLlmStatsOut(
        calls=calls, input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost_usd
    )


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


@router.get("/push/config", response_model=PushConfigOut)
async def push_config():
    """Whether Web Push is configured server-side + the VAPID public key for
    pushManager.subscribe. The frontend hides its notification control when
    enabled=false."""
    if not settings.push_configured:
        return PushConfigOut(enabled=False)
    return PushConfigOut(enabled=True, public_key=settings.vapid_public_key)


@router.post("/push/subscribe")
async def push_subscribe(body: PushSubscribeIn, session: AsyncSession = Depends(get_session)):
    """Register (or update — upsert by endpoint) a push subscription with its
    home zone. Re-POSTed on every home change; moving home resets the per-track
    danger bookkeeping so levels computed for the OLD location can't suppress
    fresh pushes for the new one."""
    sub = await session.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == body.subscription.endpoint)
    )
    if sub is None:
        sub = PushSubscription(
            endpoint=body.subscription.endpoint,
            p256dh=body.subscription.keys.p256dh,
            auth=body.subscription.keys.auth,
        )
        session.add(sub)
    else:
        sub.p256dh = body.subscription.keys.p256dh
        sub.auth = body.subscription.keys.auth
    if body.prefs is not None:
        sub.prefs = body.prefs.model_dump()
    if body.home is not None:
        home_moved = (sub.home_lat, sub.home_lon) != (body.home.lat, body.home.lon)
        sub.home_lat = body.home.lat
        sub.home_lon = body.home.lon
        sub.home_radius_km = body.home.radius_km
        sub.home_district_ids = await raion_ids_for_zone(
            session, body.home.lat, body.home.lon, body.home.radius_km
        )
        if home_moved:
            sub.danger_state = {}
    await session.commit()
    return {"ok": True}


@router.delete("/push/subscribe")
async def push_unsubscribe(body: PushUnsubscribeIn, session: AsyncSession = Depends(get_session)):
    """Idempotent: deleting an unknown endpoint is a no-op success."""
    sub = await session.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
    )
    if sub is not None:
        await session.delete(sub)
        await session.commit()
    return {"ok": True}


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

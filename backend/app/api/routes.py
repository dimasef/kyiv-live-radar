from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..auth.deps import get_optional_user, require_admin
from ..config import settings
from ..db import get_session
from ..domain.alerts import dismiss_alert, restore_alert
from ..domain.corrections import (
    parser_agrees,
    record_false_positive_for_event,
    record_false_positive_for_track,
    record_relocate_for_event,
    record_retype_for_track,
    remove_false_positives_for_track,
)
from ..domain.districts import citywide_district_id
from ..domain.home_danger import raion_ids_for_zone
from ..domain.incidents import dismiss_incident, recompute_incident_types, restore_incident
from ..domain.journal import KYIV, build_journal
from ..domain.lifecycle import close_track, reopen_track
from ..models import (
    Alert,
    District,
    GazetteerCandidate,
    Incident,
    Notice,
    ParserCorrection,
    PushSubscription,
    RawMessage,
    Source,
    Threat,
    ThreatAxis,
    ThreatEvent,
    User,
    utcnow,
)
from ..schemas import (
    AlertOut,
    AxisOut,
    CorrectionOut,
    CoverageGapOut,
    DismissedOut,
    DistrictOut,
    EventDistrictIn,
    GazetteerCandidateIn,
    GazetteerCandidateOut,
    GazetteerCandidateStatusIn,
    FeedEntryOut,
    IncidentOut,
    JournalOut,
    NoticeOut,
    PushConfigOut,
    PushSubscribeIn,
    PushUnsubscribeIn,
    RawCountOut,
    RawExportOut,
    RawLlmStatsOut,
    RawMessagesPage,
    RawSourceOut,
    ReprocessApplyIn,
    ReprocessPreviewOut,
    ReprocessResultOut,
    SourceAdminOut,
    SourceDeleteOut,
    SourceIn,
    SourceStatsOut,
    SourceUpdateIn,
    ThreatEventOut,
    ThreatOut,
    ThreatTypeIn,
)
from ..domain.sources import delete_source_cascade, upsert_source
from ..feeds.common import build_matcher
from ..feeds.telegram import request_listener_reload
from ..pipeline import reprocess as reprocess_mod
from ..pipeline.broadcast import broadcast_results
from ..pipeline.ingest import _ingest_lock
from ..pipeline.results import Broadcast
from ..timeutil import within
from .coverage import find_coverage_gaps
from .raw_query import apply_raw_filters, serialize_raw_rows
from .source_stats import SourceStats, compute_source_stats
from .serialize import alert_out as _alert_out
from .serialize import axis_out as _axis_out
from .serialize import event_out as _event_out
from .serialize import feed_entry_out as _feed_entry_out
from .serialize import incident_out as _incident_out
from .serialize import journal_out as _journal_out
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


@router.get("/journal/days", response_model=JournalOut)
async def journal_days(
    from_: Optional[str] = Query(None, alias="from", description="Start day (Kyiv), YYYY-MM-DD"),
    to: Optional[str] = Query(None, description="End day (Kyiv), YYYY-MM-DD; defaults to today"),
    session: AsyncSession = Depends(get_session),
):
    """Per-day threat activity for the journal calendar: attacks, targets,
    target-type mix, alert duration and districts touched, one row per day in
    [from, to] inclusive (zero-activity days included). Days are bucketed by
    Europe/Kyiv local date. Data volume is tiny, so whole tables are fetched and
    aggregated in Python (see domain/journal.py) — no tz-fragile SQL date math."""
    today = datetime.now(timezone.utc).astimezone(KYIV).date()
    try:
        end = date.fromisoformat(to) if to else today
        start = date.fromisoformat(from_) if from_ else end - timedelta(days=34)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date (expected YYYY-MM-DD)")
    if start > end:
        raise HTTPException(status_code=400, detail="'from' must be on or before 'to'")
    if (end - start).days > 92:
        raise HTTPException(status_code=400, detail="Range too large (max 92 days)")

    threats = list(await session.scalars(select(Threat)))
    incidents = list(await session.scalars(select(Incident)))
    alerts = list(await session.scalars(select(Alert).where(Alert.scope == "city")))
    district_events = (
        await session.execute(
            select(ThreatEvent.event_time, ThreatEvent.district_id)
            .join(Threat, ThreatEvent.threat_id == Threat.id)
            .where(Threat.closed_reason.is_distinct_from("dismissed"))
        )
    ).all()
    sentinel = await citywide_district_id(session)

    stats = build_journal(
        start,
        end,
        threats=threats,
        incidents=incidents,
        alerts=alerts,
        district_events=district_events,
        sentinel_district_id=sentinel,
    )
    return JournalOut(
        from_date=start.isoformat(),
        to_date=end.isoformat(),
        days=[_journal_out(s) for s in stats],
    )


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
    _admin: User = Depends(require_admin),
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
    _admin: User = Depends(require_admin),
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
    _admin: User = Depends(require_admin),
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
async def raw_messages_sources(
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """Channels that actually have stored raw messages, for the /raw channel
    filter dropdown. DB-driven now (subscription moved off the env lists), so it
    lists every source with data — active or not — instead of the env-configured
    set, which is empty once TELEGRAM_CHANNELS/ALERT_CHANNELS are cleared."""
    with_messages = select(RawMessage.source_id).where(RawMessage.source_id.is_not(None))
    rows = await session.scalars(
        select(Source).where(Source.id.in_(with_messages)).order_by(Source.name)
    )
    return [RawSourceOut(id=s.id, name=s.name) for s in rows]


@router.get("/raw_messages/llm_stats", response_model=RawLlmStatsOut)
async def raw_messages_llm_stats(
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
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


@router.get("/push/config", response_model=PushConfigOut)
async def push_config():
    """Whether Web Push is configured server-side + the VAPID public key for
    pushManager.subscribe. The frontend hides its notification control when
    enabled=false."""
    if not settings.push_configured:
        return PushConfigOut(enabled=False)
    return PushConfigOut(enabled=True, public_key=settings.vapid_public_key)


@router.post("/push/subscribe")
async def push_subscribe(
    body: PushSubscribeIn,
    session: AsyncSession = Depends(get_session),
    user: Optional[User] = Depends(get_optional_user),
):
    """Register (or update — upsert by endpoint) a push subscription with its
    home zone. Re-POSTed on every home change; moving home resets the per-track
    danger bookkeeping so levels computed for the OLD location can't suppress
    fresh pushes for the new one. When the request carries a valid token, the
    subscription is stamped with the owner so a user's devices can be linked."""
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
    if user is not None:
        sub.user_id = user.id
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


# ---------------------------------------------------------------------------
# Admin manual controls (require_admin) — override parser mistakes in real time:
# cancel a false-positive threat/attack/alert (soft, reversible), retype a
# track, or fix/remove a sighting. Every action commits then broadcast_results
# so all connected clients update immediately (a dismissed track drops off the
# map, journal, and stats — see domain/lifecycle.py + domain/journal.py).
# ---------------------------------------------------------------------------


async def _threat_with_events(session, threat_id: int) -> Threat | None:
    return await session.scalar(
        select(Threat)
        .where(Threat.id == threat_id)
        .options(
            selectinload(Threat.events).selectinload(ThreatEvent.district),
            selectinload(Threat.events).selectinload(ThreatEvent.source),
            selectinload(Threat.incident).selectinload(Incident.threats),
        )
    )


@router.post("/admin/threats/{threat_id}/dismiss", response_model=ThreatOut)
async def admin_dismiss_threat(
    threat_id: int,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    threat = await _threat_with_events(session, threat_id)
    if threat is None:
        raise HTTPException(status_code=404, detail="threat not found")
    close_track(threat, utcnow(), "dismissed")
    await record_false_positive_for_track(session, threat, admin.id)
    await session.commit()
    await broadcast_results(session, [Broadcast("status", threat)])
    return _threat_out(await _threat_with_events(session, threat_id))


@router.post("/admin/threats/{threat_id}/restore", response_model=ThreatOut)
async def admin_restore_threat(
    threat_id: int,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    threat = await _threat_with_events(session, threat_id)
    if threat is None:
        raise HTTPException(status_code=404, detail="threat not found")
    reopen_track(threat)
    await remove_false_positives_for_track(session, threat)
    await session.commit()
    await broadcast_results(session, [Broadcast("status", threat)])
    return _threat_out(await _threat_with_events(session, threat_id))


@router.patch("/admin/threats/{threat_id}", response_model=ThreatOut)
async def admin_retype_threat(
    threat_id: int,
    body: ThreatTypeIn,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    threat = await _threat_with_events(session, threat_id)
    if threat is None:
        raise HTTPException(status_code=404, detail="threat not found")
    threat.target_type = body.target_type
    await record_retype_for_track(session, threat, body.target_type, admin.id)
    inc = threat.incident
    if inc is not None:
        recompute_incident_types(inc)
    await session.commit()
    results = [Broadcast("status", threat)]
    if inc is not None:
        results.append(Broadcast("attack", incident=inc))
    await broadcast_results(session, results)
    return _threat_out(await _threat_with_events(session, threat_id))


@router.post("/admin/incidents/{incident_id}/dismiss", response_model=IncidentOut)
async def admin_dismiss_incident(
    incident_id: int,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    inc = await session.scalar(
        select(Incident)
        .where(Incident.id == incident_id)
        .options(selectinload(Incident.threats).selectinload(Threat.events))
    )
    if inc is None:
        raise HTTPException(status_code=404, detail="incident not found")
    dismiss_incident(inc, utcnow())
    for t in inc.threats:
        await record_false_positive_for_track(session, t, admin.id)
    await session.commit()
    results: list[Broadcast] = [Broadcast("attack", incident=inc)]
    results += [Broadcast("status", t) for t in inc.threats]
    await broadcast_results(session, results)
    sentinel_id = await citywide_district_id(session)
    return _incident_out(inc, sentinel_id)


@router.post("/admin/incidents/{incident_id}/restore", response_model=IncidentOut)
async def admin_restore_incident(
    incident_id: int,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    inc = await session.scalar(
        select(Incident)
        .where(Incident.id == incident_id)
        .options(selectinload(Incident.threats).selectinload(Threat.events))
    )
    if inc is None:
        raise HTTPException(status_code=404, detail="incident not found")
    restore_incident(inc)
    for t in inc.threats:
        await remove_false_positives_for_track(session, t)
    await session.commit()
    results: list[Broadcast] = [Broadcast("attack", incident=inc)]
    results += [Broadcast("status", t) for t in inc.threats]
    await broadcast_results(session, results)
    sentinel_id = await citywide_district_id(session)
    return _incident_out(inc, sentinel_id)


@router.post("/admin/alerts/{alert_id}/dismiss", response_model=AlertOut)
async def admin_dismiss_alert(
    alert_id: int,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    dismiss_alert(alert, utcnow())
    await session.commit()
    await broadcast_results(session, [Broadcast("alert", alert=alert)])
    return _alert_out(alert)


@router.post("/admin/alerts/{alert_id}/restore", response_model=AlertOut)
async def admin_restore_alert(
    alert_id: int,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    restore_alert(alert)
    await session.commit()
    await broadcast_results(session, [Broadcast("alert", alert=alert)])
    return _alert_out(alert)


@router.patch("/admin/events/{event_id}", response_model=ThreatOut)
async def admin_move_event(
    event_id: int,
    body: EventDistrictIn,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Reassign a sighting to a different district (fix a mislocation). The
    threat's vector/geometry are derived from its events at serialization, so a
    re-broadcast is all that's needed to update the map."""
    event = await session.get(ThreatEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    district = await session.get(District, body.district_id)
    if district is None:
        raise HTTPException(status_code=400, detail="district not found")
    await record_relocate_for_event(session, event, district, admin.id)
    event.district_id = body.district_id
    threat_id = event.threat_id
    await session.commit()
    threat = await _threat_with_events(session, threat_id)
    await broadcast_results(session, [Broadcast("status", threat)])
    return _threat_out(threat)


@router.delete("/admin/events/{event_id}", response_model=ThreatOut)
async def admin_delete_event(
    event_id: int,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Remove a wrongly-attributed sighting. If it was the track's last event,
    the now-empty track is dismissed; otherwise the parent incident's type is
    recomputed from what remains."""
    event = await session.get(ThreatEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    threat_id = event.threat_id
    # Harvest before delete — the record needs the event's source linkage.
    await record_false_positive_for_event(session, event, admin.id)
    await session.delete(event)
    await session.flush()
    threat = await _threat_with_events(session, threat_id)
    if threat is None:
        await session.commit()
        raise HTTPException(status_code=404, detail="threat not found")
    if not threat.events and threat.closed_at is None:
        close_track(threat, utcnow(), "dismissed")
    inc = threat.incident
    if inc is not None:
        recompute_incident_types(inc)
    await session.commit()
    results: list[Broadcast] = [Broadcast("status", threat)]
    if inc is not None:
        results.append(Broadcast("attack", incident=inc))
    await broadcast_results(session, results)
    return _threat_out(await _threat_with_events(session, threat_id))


@router.get("/admin/dismissed", response_model=DismissedOut)
async def admin_dismissed(
    limit: int = Query(30, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """Recently admin-cancelled threats / incidents / alerts, for the restore
    ('Повернути') list in the admin panel."""
    threats = list(
        await session.scalars(
            select(Threat)
            .where(Threat.closed_reason == "dismissed")
            .options(
                selectinload(Threat.events).selectinload(ThreatEvent.district),
                selectinload(Threat.events).selectinload(ThreatEvent.source),
            )
            .order_by(Threat.closed_at.desc())
            .limit(limit)
        )
    )
    incidents = list(
        await session.scalars(
            select(Incident)
            .where(Incident.ended_reason == "dismissed")
            .options(selectinload(Incident.threats).selectinload(Threat.events))
            .order_by(Incident.ended_at.desc())
            .limit(limit)
        )
    )
    alerts = list(
        await session.scalars(
            select(Alert)
            .where(Alert.closed_reason == "dismissed")
            .order_by(Alert.ended_at.desc())
            .limit(limit)
        )
    )
    sentinel_id = await citywide_district_id(session)
    return DismissedOut(
        threats=[_threat_out(t) for t in threats],
        incidents=[_incident_out(inc, sentinel_id) for inc in incidents],
        alerts=[_alert_out(a) for a in alerts],
    )


# ---------------------------------------------------------------------------
# Learning from corrections — turn admin actions + coverage gaps into accuracy:
# surface the messages the parser couldn't localize (gazetteer gaps), let the
# operator capture toponym candidates, and show whether the current parser has
# retired each harvested correction. See app/domain/corrections.py + coverage.py.
# ---------------------------------------------------------------------------


@router.get("/admin/coverage_gaps", response_model=list[CoverageGapOut])
async def admin_coverage_gaps(
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """Recent threat-flavored messages the parser couldn't pin to a district —
    the coverage-gap queue (usually a missing gazetteer entry)."""
    matcher = await build_matcher(session)
    return await find_coverage_gaps(session, matcher, limit=limit)


@router.post("/admin/gazetteer_candidates", response_model=GazetteerCandidateOut)
async def admin_add_gazetteer_candidate(
    body: GazetteerCandidateIn,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Capture a toponym candidate from a gap — NOT a live gazetteer edit; that
    stays a reviewed code step with a stem-collision sweep (CLAUDE.md)."""
    text = ""
    if body.raw_message_id is not None:
        raw = await session.get(RawMessage, body.raw_message_id)
        if raw is None:
            raise HTTPException(status_code=400, detail="raw message not found")
        text = raw.text
    cand = GazetteerCandidate(
        raw_message_id=body.raw_message_id,
        text=text,
        suggested_name=body.suggested_name,
        note=body.note,
        created_by_user_id=admin.id,
    )
    session.add(cand)
    await session.commit()
    return cand


@router.get("/admin/gazetteer_candidates", response_model=list[GazetteerCandidateOut])
async def admin_list_gazetteer_candidates(
    status: Optional[str] = Query(None, description="Filter by status"),
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    stmt = select(GazetteerCandidate).order_by(GazetteerCandidate.created_at.desc())
    if status is not None:
        stmt = stmt.where(GazetteerCandidate.status == status)
    return list(await session.scalars(stmt))


@router.patch("/admin/gazetteer_candidates/{candidate_id}", response_model=GazetteerCandidateOut)
async def admin_update_gazetteer_candidate(
    candidate_id: int,
    body: GazetteerCandidateStatusIn,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    cand = await session.get(GazetteerCandidate, candidate_id)
    if cand is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    cand.status = body.status
    await session.commit()
    return cand


@router.get("/admin/corrections", response_model=list[CorrectionOut])
async def admin_corrections(
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """Harvested corrections + whether the CURRENT parser already agrees — so
    the operator sees which mistakes are retired vs still reproduced."""
    matcher = await build_matcher(session)
    id_to_en = {d.id: d.name_en for d in await session.scalars(select(District))}
    rows = list(
        await session.scalars(
            select(ParserCorrection).order_by(ParserCorrection.created_at.desc()).limit(limit)
        )
    )
    out = []
    for c in rows:
        agrees, _ = parser_agrees(c, matcher, id_to_en)
        out.append(
            CorrectionOut(
                id=c.id,
                raw_message_id=c.raw_message_id,
                text=c.text,
                kind=c.kind,
                expected=c.expected or {},
                origin=c.origin,
                created_at=c.created_at,
                resolved=agrees,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Admin-triggered reprocess — apply the CURRENT parser to all stored raw
# messages without the REPROCESS_ON_BOOT env+restart footgun. Guarded: runs
# under the ingest lock (never races the live listener) and refuses mid-attack
# by default. Returns a before/after diff so the operator sees the effect.
# ---------------------------------------------------------------------------


async def _reprocess_summary(s) -> dict:
    """Totals + recent per-day target/track counts (reuses the journal
    aggregation, so it matches what the operator sees on /journal)."""
    tracks = await s.scalar(select(func.count()).select_from(Threat))
    events = await s.scalar(select(func.count()).select_from(ThreatEvent))
    incidents = await s.scalar(select(func.count()).select_from(Incident))
    today = datetime.now(timezone.utc).astimezone(KYIV).date()
    start = today - timedelta(days=20)
    threats = list(await s.scalars(select(Threat)))
    incs = list(await s.scalars(select(Incident)))
    alerts = list(await s.scalars(select(Alert).where(Alert.scope == "city")))
    district_events = (
        await s.execute(
            select(ThreatEvent.event_time, ThreatEvent.district_id)
            .join(Threat, ThreatEvent.threat_id == Threat.id)
            .where(Threat.closed_reason.is_distinct_from("dismissed"))
        )
    ).all()
    sentinel = await citywide_district_id(s)
    stats = build_journal(
        start, today, threats=threats, incidents=incs, alerts=alerts,
        district_events=district_events, sentinel_district_id=sentinel,
    )
    return {
        "tracks": tracks or 0,
        "events": events or 0,
        "incidents": incidents or 0,
        "days": [
            {"date": d.date, "target_count": d.target_count, "track_count": d.track_count}
            for d in stats
        ],
    }


async def _attack_active(s) -> bool:
    open_inc = await s.scalar(select(Incident.id).where(Incident.ended_at.is_(None)))
    open_alert = await s.scalar(
        select(Alert.id).where(Alert.ended_at.is_(None), Alert.scope == "city")
    )
    return open_inc is not None or open_alert is not None


@router.get("/admin/reprocess/preview", response_model=ReprocessPreviewOut)
async def admin_reprocess_preview(_admin: User = Depends(require_admin)):
    """Pre-flight scope: how many raw messages will replay, the current counts
    that will be rebuilt, and whether an attack is active (a reprocess would be
    ill-timed). Read-only. Uses reprocess's own SessionLocal so it reads exactly
    the DB the apply would rebuild."""
    async with reprocess_mod.SessionLocal() as s:
        raw_count = await s.scalar(select(func.count()).select_from(RawMessage))
        current = await _reprocess_summary(s)
        attack = await _attack_active(s)
    return ReprocessPreviewOut(raw_messages=raw_count or 0, current=current, attack_active=attack)


@router.post("/admin/reprocess/apply", response_model=ReprocessResultOut)
async def admin_reprocess_apply(
    body: ReprocessApplyIn,
    _admin: User = Depends(require_admin),
):
    """Wipe + rebuild all tracks/incidents from raw_messages through the current
    pipeline. Held under `_ingest_lock` so the live listener can't ingest into a
    half-rebuilt DB (messages queue behind it and process after). Refuses while
    an attack is active unless `force`. raw_messages are preserved, so a
    reprocess is repeatable."""
    async with reprocess_mod.SessionLocal() as s:
        if not body.force and await _attack_active(s):
            raise HTTPException(
                status_code=409,
                detail="attack active — reprocess now would disrupt live tracking (pass force)",
            )
        before = await _reprocess_summary(s)
    async with _ingest_lock:
        result = await reprocess_mod.run_reprocess(no_llm=body.no_llm)
    async with reprocess_mod.SessionLocal() as s:
        after = await _reprocess_summary(s)
    return ReprocessResultOut(before=before, after=after, result=result)


# --- Sources / channels management (admin) --------------------------------
# The DB's active Sources ARE the live channel list (feeds/telegram.py reads
# them); mutations here signal the listener to reconnect and re-subscribe.


def _source_admin_out(src: Source, stats: dict[int, SourceStats]) -> SourceAdminOut:
    st = stats.get(src.id) or SourceStats()
    return SourceAdminOut(
        id=src.id,
        channel_key=src.channel_key,
        name=src.name,
        subscribe_ref=src.subscribe_ref,
        role=src.role,
        is_active=src.is_active,
        trust_weight=src.trust_weight,
        last_listener_error=src.last_listener_error,
        created_at=src.created_at,
        stats=SourceStatsOut(
            messages_total=st.messages_total,
            messages_processed=st.messages_processed,
            events_produced=st.events_produced,
            llm_fallback_rate=st.llm_fallback_rate,
            coverage_rate=st.coverage_rate,
            correction_rate=st.correction_rate,
            conflict_share=st.conflict_share,
            quality_score=st.quality_score,
            last_message_at=st.last_message_at,
        ),
    )


@router.get("/admin/sources", response_model=list[SourceAdminOut])
async def admin_list_sources(
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """Every source with its on-demand quality stats — active channels first,
    then by name. Inactive rows are kept (removal is a soft deactivate) so the
    operator can re-enable or inspect a channel's history."""
    stats = await compute_source_stats(session)
    rows = list(await session.scalars(select(Source)))
    rows.sort(key=lambda s: (not s.is_active, s.name.lower()))
    return [_source_admin_out(s, stats) for s in rows]


@router.post("/admin/sources", response_model=SourceAdminOut)
async def admin_add_source(
    body: SourceIn,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Add (or reactivate) a channel and tell the listener to re-subscribe. Whether
    it actually starts delivering shows up as message counts / last_listener_error
    on the next connect."""
    src = await upsert_source(
        session,
        subscribe_ref=body.subscribe_ref,
        name=body.name,
        role=body.role,
        trust_weight=body.trust_weight,
        user_id=admin.id,
    )
    await session.commit()
    request_listener_reload()
    stats = await compute_source_stats(session)
    return _source_admin_out(src, stats)


@router.patch("/admin/sources/{source_id}", response_model=SourceAdminOut)
async def admin_update_source(
    source_id: int,
    body: SourceUpdateIn,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """Edit a source's name / role / trust_weight / active flag. Only a change that
    affects what's watched (role or is_active) triggers a listener reload."""
    src = await session.get(Source, source_id)
    if src is None:
        raise HTTPException(status_code=404, detail="source not found")
    reload_needed = False
    if body.name is not None:
        src.name = body.name
    if body.role is not None and body.role != src.role:
        src.role = body.role
        reload_needed = True
    if body.trust_weight is not None:
        src.trust_weight = body.trust_weight
    if body.is_active is not None and body.is_active != src.is_active:
        src.is_active = body.is_active
        reload_needed = True
    await session.commit()
    if reload_needed:
        request_listener_reload()
    stats = await compute_source_stats(session)
    return _source_admin_out(src, stats)


@router.post("/admin/sources/{source_id}/deactivate", response_model=SourceAdminOut)
async def admin_deactivate_source(
    source_id: int,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """Remove a channel from the live feed (soft — the row stays, since
    raw_messages/threat_events reference it and its history stays queryable)."""
    return await _set_source_active(session, source_id, active=False)


@router.post("/admin/sources/{source_id}/activate", response_model=SourceAdminOut)
async def admin_activate_source(
    source_id: int,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    return await _set_source_active(session, source_id, active=True)


async def _set_source_active(session: AsyncSession, source_id: int, *, active: bool) -> SourceAdminOut:
    src = await session.get(Source, source_id)
    if src is None:
        raise HTTPException(status_code=404, detail="source not found")
    if src.is_active != active:
        src.is_active = active
        await session.commit()
        request_listener_reload()
    stats = await compute_source_stats(session)
    return _source_admin_out(src, stats)


@router.delete("/admin/sources/{source_id}", response_model=SourceDeleteOut)
async def admin_delete_source(
    source_id: int,
    force: bool = Query(False, description="Delete even while an attack is active"),
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """HARD-delete a channel AND all of its stored data (raw_messages, notices,
    threat_events), repairing the tracks/incidents it touched — irreversible,
    unlike deactivate. Refused while an attack is active (the graph surgery would
    disrupt live tracking) unless `force`."""
    if not force and await _attack_active(session):
        raise HTTPException(
            status_code=409,
            detail="attack active — deleting a source now would disrupt live tracking (pass force)",
        )
    result = await delete_source_cascade(session, source_id)
    if result is None:
        raise HTTPException(status_code=404, detail="source not found")
    request_listener_reload()
    return SourceDeleteOut(**result)

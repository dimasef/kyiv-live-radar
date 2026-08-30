"""Admin parser overrides: cancel/restore a false-positive threat, attack or
alert, retype a track, fix or delete a sighting, and list what was dismissed."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...auth.deps import require_admin
from ...db import get_session
from ...domain.alerts import dismiss_alert, restore_alert
from ...domain.corrections import (
    record_false_positive_for_event,
    record_false_positive_for_track,
    record_relocate_for_event,
    record_retype_for_track,
    remove_false_positives_for_track,
)
from ...domain.districts import citywide_district_id, district_regions
from ...domain.incidents import dismiss_incident, recompute_incident_types, restore_incident
from ...domain.lifecycle import close_track, reopen_track
from ...domain.tracking import set_fusion
from ...models import (
    Alert,
    District,
    Incident,
    Notice,
    RawMessage,
    Threat,
    ThreatEvent,
    User,
    utcnow,
)
from ...pipeline.broadcast import broadcast_results
from ...pipeline.ingest import note_operator_type
from ...pipeline.results import Broadcast
from ...schemas import (
    AlertOut,
    DismissedOut,
    EventDistrictIn,
    EventTrackIn,
    IncidentOut,
    IncidentTypeIn,
    NoticeOut,
    RawNoticeIn,
    RegroupOut,
    ThreatOut,
    ThreatTypeIn,
)
from ...timeutil import naive
from ..deps import _threat_with_events
from ..serialize import alert_out as _alert_out
from ..serialize import incident_out as _incident_out
from ..serialize import notice_out as _notice_out
from ..serialize import threat_out as _threat_out

router = APIRouter()


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


@router.get("/admin/threats/{threat_id}", response_model=ThreatOut)
async def admin_threat(
    threat_id: int,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """One track with all its sightings — what the track editor opens on.

    The public `/threats/{id}/events` cannot serve this: it withholds impacts
    and returns no track state (type, lifecycle, fusion), both of which are
    exactly what an operator is here to inspect and fix. Impact privacy is a
    rule about the public map, feed and journal (tests/test_impact_privacy.py);
    this route is behind require_admin and shows the operator the same rows the
    admin feed at /raw already lists for them.
    """
    threat = await _threat_with_events(session, threat_id)
    if threat is None:
        raise HTTPException(status_code=404, detail="threat not found")
    return _threat_out(threat)


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
    # …and tell the LIVE pipeline, not just the regression dataset. An operator
    # correcting an open track is the strongest type signal the system gets, and
    # it used to stop at the track: on 2026-08-23 a retype to jet_drone at
    # 18:50:12.7 was followed 5.7s later by a classifier call that answered
    # `shahed` and became the channel context, because a machine guess seeds it
    # and a human's correction did not. Open tracks only — retyping a closed one
    # is a history fix, and must not speak about the sky right now.
    if threat.closed_at is None:
        note_operator_type({e.source_id for e in threat.events}, body.target_type, utcnow())
    inc = threat.incident
    if inc is not None:
        recompute_incident_types(inc)
    await session.commit()
    results = [Broadcast("status", threat)]
    if inc is not None:
        results.append(Broadcast("attack", incident=inc))
    await broadcast_results(session, results)
    return _threat_out(await _threat_with_events(session, threat_id))


@router.patch("/admin/incidents/{incident_id}/type", response_model=IncidentOut)
async def admin_retype_incident(
    incident_id: int,
    body: IncidentTypeIn,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """Set what is in the air, overriding the types derived from the member
    tracks — an empty list hands the attack back to that derivation.

    A list because a raid is not always one thing. Naming two weapon families is
    how the operator says 'комбінована': `attack.classify` reads the same field
    it always reads and reaches that label itself, so a manual verdict and a
    derived one are indistinguishable downstream.

    Deliberately does NOT retype the member tracks. They are separate claims:
    each track says what a spotter reported over one district, the attack says
    what the raid as a whole is. A ballistic verdict on a raid that also carried
    shaheds must not rewrite the shahed sightings into ballistic ones — the map,
    the feed and the regression dataset would all then be wrong about the sky.
    Retyping one track is its own action (PATCH /admin/threats/{id}).

    For the same reason no ParserCorrection is recorded: this is a judgement
    about a rollup, not a labelled example of a message the parser misread.
    """
    inc = await session.scalar(
        select(Incident)
        .where(Incident.id == incident_id)
        .options(selectinload(Incident.threats).selectinload(Threat.events))
    )
    if inc is None:
        raise HTTPException(status_code=404, detail="incident not found")
    # Empty list stores NULL, not [], so "no override" has ONE representation —
    # `recompute_incident_types` and the published `type_override` both read
    # falsy either way, but two spellings of the same state invite a future
    # `is not None` check that gets it wrong.
    inc.type_override = list(body.target_types) or None
    # Both directions run through here: setting an override applies it, and
    # clearing one re-derives from the members in the same call.
    recompute_incident_types(inc)
    await session.commit()
    await broadcast_results(session, [Broadcast("attack", incident=inc)])
    sentinel_id = await citywide_district_id(session)
    return _incident_out(inc, sentinel_id)


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
    await _resync_track_region(session, threat)
    await broadcast_results(session, [Broadcast("status", threat)])
    return _threat_out(threat)


async def _resync_track_region(session, threat: Threat | None) -> None:
    """Put a track back in the region of its LATEST sighting.

    Ingest keeps that invariant as the target moves (handlers._hand_over_region);
    an admin relocating or deleting a sighting can break it, leaving the track
    corroborating and closing in a pool it no longer belongs to."""
    if threat is None or not threat.events:
        return
    # naive(): see timeutil — DB-loaded events are naive, one added in the
    # current session is aware, and max() across the two raises TypeError.
    latest = max(threat.events, key=lambda e: naive(e.event_time))
    region = (await district_regions(session)).get(latest.district_id)
    if region and threat.region != region:
        threat.region = region
        await session.commit()


def _split_track_from(source: Threat, event: ThreatEvent) -> Threat:
    """A new track carrying `event` alone, cloned from the track it is leaving.

    Lifecycle and incident are INHERITED rather than started fresh: splitting a
    track the sweeper closed an hour ago must produce a second closed track, not
    a brand-new live dot on the map for a target that is long gone. Type and
    group size come from the event itself where it has them — that is the
    sighting's own reading, and preferring it is the whole point of splitting.
    """
    return Threat(
        created_at=event.event_time,
        incident_id=source.incident_id,
        target_type=event.event_target_type or source.target_type,
        status=source.status,
        kind="track",
        scope=source.scope,
        region=source.region,
        target_count=event.event_target_count or 1,
        closed_at=source.closed_at,
        closed_reason=source.closed_reason,
    )


@router.patch("/admin/events/{event_id}/threat", response_model=RegroupOut)
async def admin_regroup_event(
    event_id: int,
    body: EventTrackIn,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """Move a sighting onto another track, or split it out onto its own.

    Tracking groups sightings by reply-chain and then same-district
    corroboration (domain/tracking.py), and its two failure modes are exactly
    these two shapes: one real target split across several tracks, or several
    targets merged into one. Until now the only repair was DELETING the
    sighting, which throws away a real observation to fix a grouping mistake.

    Deliberately not recorded as a ParserCorrection: that dataset labels what
    the PARSER should have produced (type, district, suppression), and grouping
    is not the parser's decision. Track-level ground truth lives in
    eval/ground_truth_sessions.json.
    """
    event = await session.get(ThreatEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    if body.threat_id == event.threat_id:
        raise HTTPException(status_code=400, detail="sighting is already on that track")
    source = await _threat_with_events(session, event.threat_id)
    if source is None:
        raise HTTPException(status_code=404, detail="threat not found")

    if body.threat_id is None:
        target = _split_track_from(source, event)
        # Left PENDING on purpose — no flush here. A flushed-but-never-loaded
        # `events` collection is a lazy load, and lazy loads raise MissingGreenlet
        # on the async session; while the track is pending the backref below just
        # fills an empty collection with no I/O at all.
        session.add(target)
    else:
        target = await _threat_with_events(session, body.threat_id)
        if target is None:
            raise HTTPException(status_code=400, detail="target track not found")
        # An impact is a terminal marker, not a path being followed — grouping a
        # sighting into one would make it claim a movement it never had (and
        # impacts are withheld from the map by design, so the sighting would
        # vanish from it). See tests/test_impact_privacy.py.
        if target.kind != "track":
            raise HTTPException(status_code=400, detail="target is not a track")

    # Assign through the RELATIONSHIP, not the foreign key: that is what keeps
    # both in-memory `events` collections right, so the fusion recompute below
    # sees the post-move membership instead of the stale pre-move one.
    event.threat = target
    await session.flush()

    # An emptied source track is a track that no longer describes anything.
    if not source.events and source.closed_at is None:
        close_track(source, utcnow(), "dismissed")
    incidents: dict[int, Incident] = {}
    for track in (source, target):
        set_fusion(track)
        if track.incident is not None:
            recompute_incident_types(track.incident)
            incidents[track.incident.id] = track.incident
    await session.commit()
    # Region follows the LATEST sighting on each side, and the move changed
    # which sighting that is for both of them.
    await _resync_track_region(session, source)
    await _resync_track_region(session, target)

    results: list[Broadcast] = [Broadcast("status", target), Broadcast("status", source)]
    results += [Broadcast("attack", incident=inc) for inc in incidents.values()]
    await broadcast_results(session, results)
    return RegroupOut(
        event_id=event_id,
        threat=_threat_out(await _threat_with_events(session, target.id)),
        source_threat=_threat_out(await _threat_with_events(session, source.id)),
    )


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
    else:
        # The deleted sighting counted toward corroboration/confidence; leaving
        # those be would have the track (and its chip in «Весь фід») still claim
        # a source that no longer exists.
        set_fusion(threat)
    inc = threat.incident
    if inc is not None:
        recompute_incident_types(inc)
    await session.commit()
    await _resync_track_region(session, threat)
    results: list[Broadcast] = [Broadcast("status", threat)]
    if inc is not None:
        results.append(Broadcast("attack", incident=inc))
    await broadcast_results(session, results)
    return _threat_out(await _threat_with_events(session, threat_id))


@router.post("/admin/raw_messages/{raw_id}/notice", response_model=NoticeOut)
async def admin_add_notice(
    raw_id: int,
    body: RawNoticeIn,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """Publish a raw message to the feed as a notice — the counterpart of taking
    an event off one.

    The suppression filters are tuned to keep the feed clean, so they also drop
    things worth reading: a forecast of the next wave, a channel's own «відбій»
    phrased unusually, a situation summary. Rather than loosening a filter for
    one phrasing, the operator publishes that message by hand.

    `generated_by` stays 'rule': that flag drives the feed's "AI · неперевірено"
    badge, and a human decision is not the thing that badge warns about."""
    raw = await session.get(RawMessage, raw_id)
    if raw is None:
        raise HTTPException(status_code=404, detail="raw message not found")
    # /raw_messages links a row to its notice by (source, message id), and shows
    # exactly one — a second would be invisible from the very page it was added
    # on. Messages with no channel id (replayed/synthetic) can't be linked at
    # all, so nothing to check.
    if raw.message_id is not None:
        existing = await session.scalar(
            select(Notice).where(
                Notice.source_id.is_not_distinct_from(raw.source_id),
                Notice.source_message_id == raw.message_id,
            )
        )
        if existing is not None:
            raise HTTPException(status_code=409, detail="message already has a notice")
    notice = Notice(
        kind=body.kind,
        text=(body.text or raw.text or "").strip(),
        event_time=raw.event_time,
        source_id=raw.source_id,
        source_message_id=raw.message_id,
    )
    session.add(notice)
    await session.commit()
    await broadcast_results(session, [Broadcast("notice", notice=notice)])
    loaded = await session.scalar(
        select(Notice).where(Notice.id == notice.id).options(selectinload(Notice.source))
    )
    return _notice_out(loaded)


@router.delete("/admin/notices/{notice_id}", status_code=204)
async def admin_delete_notice(
    notice_id: int,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """Take a notice off the feed — a wrong all-clear, or one added by hand and
    thought better of. Nothing is broadcast: the feed has no "notice removed"
    frame, and a card that disappears only on the next load is better than one
    that vanishes under a reader mid-raid."""
    notice = await session.get(Notice, notice_id)
    if notice is None:
        raise HTTPException(status_code=404, detail="notice not found")
    await session.delete(notice)
    await session.commit()


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

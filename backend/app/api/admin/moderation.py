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
from ...domain.districts import citywide_district_id
from ...domain.incidents import dismiss_incident, recompute_incident_types, restore_incident
from ...domain.lifecycle import close_track, reopen_track
from ...models import (
    Alert,
    District,
    Incident,
    Threat,
    ThreatEvent,
    User,
    utcnow,
)
from ...pipeline.broadcast import broadcast_results
from ...pipeline.results import Broadcast
from ...schemas import (
    AlertOut,
    DismissedOut,
    EventDistrictIn,
    IncidentOut,
    ThreatOut,
    ThreatTypeIn,
)
from ..deps import _threat_with_events
from ..serialize import alert_out as _alert_out
from ..serialize import incident_out as _incident_out
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

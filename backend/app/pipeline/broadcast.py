"""Turn ingest results into WebSocket broadcasts (in-process, single instance).

For the production two-service model (separate api + worker) this fan-out moves
to Redis / Postgres LISTEN-NOTIFY; the ingest pipeline stays unchanged.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..api.serialize import alert_out, event_out, incident_out, notice_out, threat_out
from ..api.ws import manager
from ..domain.districts import citywide_district_id
from ..models import Incident, Notice, Threat, ThreatEvent
from ..schemas import WSMessage
from .results import Broadcast


async def _load_full(session, threat_id: int) -> Threat | None:
    stmt = (
        select(Threat)
        .where(Threat.id == threat_id)
        .options(
            selectinload(Threat.events).selectinload(ThreatEvent.district),
            selectinload(Threat.events).selectinload(ThreatEvent.source),
        )
    )
    return await session.scalar(stmt)


async def _load_incident_full(session, incident_id: int) -> Incident | None:
    stmt = (
        select(Incident)
        .where(Incident.id == incident_id)
        .options(selectinload(Incident.threats).selectinload(Threat.events))
    )
    return await session.scalar(stmt)


async def broadcast_results(session, results: list[Broadcast]) -> None:
    for b in results:
        if b.type == "notice" and b.notice is not None:
            n = await session.scalar(
                select(Notice).where(Notice.id == b.notice.id).options(selectinload(Notice.source))
            )
            if n is not None:
                await manager.broadcast(WSMessage(type="notice", notice=notice_out(n)))
            continue
        if b.type == "alert" and b.alert is not None:
            await manager.broadcast(WSMessage(type="alert", alert=alert_out(b.alert)))
            continue
        if b.type == "attack" and b.incident is not None:
            inc = await _load_incident_full(session, b.incident.id)
            if inc is not None:
                sentinel_id = await citywide_district_id(session)
                await manager.broadcast(
                    WSMessage(type="attack", incident=incident_out(inc, sentinel_id))
                )
            continue
        if b.threat is None:
            continue
        threat = await _load_full(session, b.threat.id)
        if threat is None:
            continue
        ev_out = None
        if b.event is not None:
            match = next((e for e in threat.events if e.id == b.event.id), None)
            if match is not None:
                ev_out = event_out(match)
        await manager.broadcast(
            WSMessage(type=b.type, threat=threat_out(threat), event=ev_out)
        )

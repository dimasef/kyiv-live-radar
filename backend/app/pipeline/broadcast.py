"""Turn ingest results into WebSocket broadcasts (in-process, single instance).

For the production two-service model (separate api + worker) this fan-out moves
to Redis / Postgres LISTEN-NOTIFY; the ingest pipeline stays unchanged.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..api.serialize import alert_out, axis_out, event_out, incident_out, notice_out, threat_out
from ..api.ws import manager
from ..domain.districts import citywide_district_id
from ..models import Incident, Notice, Threat, ThreatEvent
from ..schemas import WSMessage
from .home_push import evaluate_home_danger, evaluate_regional_ballistic
from .results import Broadcast

log = logging.getLogger("broadcast")


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
    # One message about several raions produces one Broadcast per raion for the
    # SAME track (handlers._handle_sighting), so without these two the fan-out
    # re-read the whole track and re-ran the danger assessment — which scans
    # every push subscription — once per raion named.
    loaded: dict[int, Threat | None] = {}
    danger_seen: set[int] = set()

    for b in results:
        log.debug("broadcasting %s", b.type)
        if b.type == "notice" and b.notice is not None:
            n = await session.scalar(
                select(Notice).where(Notice.id == b.notice.id).options(selectinload(Notice.source))
            )
            if n is not None:
                await manager.broadcast(WSMessage(type="notice", notice=notice_out(n)))
                try:
                    await evaluate_regional_ballistic(session, n)
                except Exception:
                    # Same rule as the track branch: push is supplementary and
                    # must never break WS fan-out.
                    log.exception("regional ballistic evaluation failed for notice %s", n.id)
            continue
        if b.type == "alert" and b.alert is not None:
            await manager.broadcast(WSMessage(type="alert", alert=alert_out(b.alert)))
            continue
        if b.type == "axis" and b.axis is not None:
            await manager.broadcast(WSMessage(type="axis", axis=axis_out(b.axis)))
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
        if b.threat.id not in loaded:
            loaded[b.threat.id] = await _load_full(session, b.threat.id)
        threat = loaded[b.threat.id]
        if threat is None:
            continue
        # Impact markers never reach a client live — see api/public/threats.py
        # for why. Filtering here (rather than at each producer) means a new
        # code path that broadcasts an impact can't reintroduce the leak.
        if threat.kind == "impact":
            continue
        ev_out = None
        if b.event is not None:
            match = next((e for e in threat.events if e.id == b.event.id), None)
            if match is not None:
                ev_out = event_out(match)
        await manager.broadcast(
            WSMessage(type=b.type, threat=threat_out(threat), event=ev_out)
        )
        if threat.id in danger_seen:
            continue
        danger_seen.add(threat.id)
        try:
            await evaluate_home_danger(session, threat)
        except Exception:
            # Push is supplementary — a failure here must never break WS fan-out.
            log.exception("home danger evaluation failed for threat %s", threat.id)

"""Turn ingest results into WebSocket broadcasts (in-process, single instance).

For the production two-service model (separate api + worker) this fan-out moves
to Redis / Postgres LISTEN-NOTIFY; the ingest pipeline stays unchanged.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .api.ws import manager
from .ingest import Broadcast
from .models import Notice, Threat, ThreatEvent
from .schemas import WSMessage
from .serialize import event_out, notice_out, threat_out


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


async def broadcast_results(session, results: list[Broadcast]) -> None:
    for b in results:
        if b.type == "notice" and b.notice is not None:
            n = await session.scalar(
                select(Notice).where(Notice.id == b.notice.id).options(selectinload(Notice.source))
            )
            if n is not None:
                await manager.broadcast(WSMessage(type="notice", notice=notice_out(n)))
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

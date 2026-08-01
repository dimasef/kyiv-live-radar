"""Helpers shared by more than one router module."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..models import (
    Alert,
    Incident,
    Threat,
    ThreatEvent,
)


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


async def _attack_active(s) -> bool:
    open_inc = await s.scalar(select(Incident.id).where(Incident.ended_at.is_(None)))
    open_alert = await s.scalar(
        select(Alert.id).where(Alert.ended_at.is_(None), Alert.scope == "city")
    )
    return open_inc is not None or open_alert is not None

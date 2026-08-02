"""Helpers shared by more than one router module."""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import (
    Alert,
    Friendship,
    Incident,
    Threat,
    ThreatEvent,
)


async def are_friends(session: AsyncSession, a: int, b: int) -> bool:
    """An accepted edge either way round. The gate on everything one user is
    allowed to see about another — a collection, a contact list — so it lives
    here rather than being re-implemented per router."""
    edge = await session.scalar(
        select(Friendship).where(
            Friendship.status == "accepted",
            or_(
                (Friendship.requester_id == a) & (Friendship.addressee_id == b),
                (Friendship.requester_id == b) & (Friendship.addressee_id == a),
            ),
        )
    )
    return edge is not None


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

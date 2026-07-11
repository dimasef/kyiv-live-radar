"""Incident grouping (Stage E): fold the tracks / impacts / city-wide alerts of
one attack into a single "incident" umbrella ("one alert = one incident").

An incident is opened by the first threat of an attack and joined by every
later threat while the incident is still fresh (``incident_gap_minutes``). It is
ended by a full all-clear or by the stale sweeper once activity lapses. Its
aggregate counts are derived from member threats at serialization time (see
api/routes.py), not stored here.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .config import settings
from .models import Incident, Threat

# Target-type severity — an incident is labelled by its most dangerous member.
_SEVERITY = {"unknown": 0, "shahed": 1, "jet_drone": 2, "missile": 3, "ballistic": 4}


def _more_severe(a: str, b: str) -> str:
    return a if _SEVERITY.get(a, 0) >= _SEVERITY.get(b, 0) else b


def _within(a: datetime, b: datetime, gap: timedelta) -> bool:
    an = a.replace(tzinfo=None) if a.tzinfo is not None else a
    bn = b.replace(tzinfo=None) if b.tzinfo is not None else b
    return abs((bn - an).total_seconds()) <= gap.total_seconds()


async def find_active_incident(session, when: datetime) -> Incident | None:
    """The current open incident, if it saw activity within the gap window."""
    gap = timedelta(minutes=settings.incident_gap_minutes)
    stmt = (
        select(Incident)
        .where(Incident.ended_at.is_(None))
        .order_by(Incident.started_at.desc())
    )
    for inc in await session.scalars(stmt):
        if _within(inc.last_activity_at, when, gap):
            return inc
    return None


async def attach_to_incident(session, threat: Threat, when: datetime) -> Incident:
    """Attach `threat` to the current open incident (creating one if none is
    active), refresh the incident's recency, and raise its severity label to the
    most dangerous member. Idempotent for a threat already on that incident."""
    inc = await find_active_incident(session, when)
    if inc is None:
        inc = Incident(started_at=when, last_activity_at=when, target_type=threat.target_type)
        session.add(inc)
        await session.commit()
    threat.incident_id = inc.id
    inc.target_type = _more_severe(inc.target_type, threat.target_type)
    inc.last_activity_at = _later(inc.last_activity_at, when)
    await session.commit()
    return inc


def _later(a: datetime, b: datetime) -> datetime:
    an = a.replace(tzinfo=None) if a.tzinfo is not None else a
    bn = b.replace(tzinfo=None) if b.tzinfo is not None else b
    return a if an >= bn else b


async def end_active_incidents(session, when: datetime) -> list[Incident]:
    """End every open incident — used on a full all-clear ("Відбій тривоги")."""
    incs = list(await session.scalars(select(Incident).where(Incident.ended_at.is_(None))))
    for inc in incs:
        inc.ended_at = when
    if incs:
        await session.commit()
    return incs


async def close_stale_incidents(session, now: datetime, minutes: int) -> list[Incident]:
    """End incidents whose last member activity is older than `minutes` — an
    attack that quietly petered out without an explicit all-clear."""
    stale_gap = timedelta(minutes=minutes)
    incs = list(await session.scalars(select(Incident).where(Incident.ended_at.is_(None))))
    ended = []
    for inc in incs:
        if not _within(inc.last_activity_at, now, stale_gap):
            inc.ended_at = now
            ended.append(inc)
    if ended:
        await session.commit()
    return ended

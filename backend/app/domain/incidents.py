"""Incident grouping (Stage E): fold the tracks / impacts / city-wide alerts of
one attack into a single "incident" umbrella ("one alert = one incident").

An incident is opened by the first threat of an attack and joined by every
later threat while the incident is still fresh (``incident_gap_minutes``). It is
ended by a full all-clear or by the stale sweeper once activity lapses. Its
aggregate counts are derived from member threats at serialization time (see
api/routes.py), not stored here.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..config import settings
from ..models import Alert, Incident, Threat
from .lifecycle import close_track, reopen_track

log = logging.getLogger("incidents")

# Target-type severity — an incident is labelled by its most dangerous member.
_SEVERITY = {"unknown": 0, "shahed": 1, "jet_drone": 2, "missile": 3, "ballistic": 4}


def recompute_incident_types(inc: Incident) -> None:
    """Rebuild `attack_types`/`target_type` from the incident's CURRENT member
    threats — needed after an admin retypes or removes a member track, where the
    accumulate-only `attach_to_incident` path can't shrink the set. Requires
    `inc.threats` to be loaded (selectinload). Ignores dismissed tracks so a
    cancelled false positive can't keep an obsolete type alive."""
    types = sorted(
        {
            t.target_type
            for t in inc.threats
            if t.target_type not in (None, "unknown")
            and t.closed_reason != "dismissed"
        },
        key=lambda tt: _SEVERITY.get(tt, 0),
    )
    inc.attack_types = types
    inc.target_type = types[-1] if types else "unknown"


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


async def attach_to_incident(
    session, threat: Threat, when: datetime, decoy: bool = False, hypersonic: bool = False
) -> Incident:
    """Attach `threat` to the current open incident (creating one if none is
    active), refresh the incident's recency, and raise its severity label to
    the most dangerous member. Idempotent for a threat already on that
    incident.

    `decoy`/`hypersonic` come from the triggering message's ParseResult
    (parser.py) — accumulated onto the incident as decoy_mentions/
    has_hypersonic for app/attack.py::classify to derive from later. A brand
    new incident links the currently open CITY alert, if any (the reverse
    direction — a ballistic incident that starts BEFORE the siren — is
    handled by alerts.py's adoption on alert start)."""
    inc = await find_active_incident(session, when)
    if inc is None:
        alert_id = await session.scalar(
            select(Alert.id).where(Alert.scope == "city", Alert.ended_at.is_(None))
        )
        inc = Incident(
            started_at=when, last_activity_at=when, target_type=threat.target_type,
            alert_id=alert_id,
        )
        session.add(inc)
        await session.commit()
        log.info("incident %s started (target_type=%s)", inc.id, inc.target_type)
    threat.incident_id = inc.id
    if decoy:
        inc.decoy_mentions += 1
    if hypersonic:
        inc.has_hypersonic = True
    inc.last_activity_at = _later(inc.last_activity_at, when)
    await session.commit()
    # Rebuild target_type/attack_types from the CURRENT members instead of
    # appending — so a track that upgraded its type mid-flight (missile ->
    # ballistic, see ingest._upgrade_type) leaves ONE type, not both, and the
    # incident no longer reads as a false 'combined' (the WORKFLOW.md /
    # attack.py::classify known compromise).
    await session.refresh(inc, ["threats"])
    recompute_incident_types(inc)
    await session.commit()
    return inc


def _later(a: datetime, b: datetime) -> datetime:
    an = a.replace(tzinfo=None) if a.tzinfo is not None else a
    bn = b.replace(tzinfo=None) if b.tzinfo is not None else b
    return a if an >= bn else b


def dismiss_incident(inc: Incident, when: datetime) -> None:
    """Admin cancel of a false-positive attack: end the incident with reason
    'dismissed' AND cancel every still-open member track. Requires `inc.threats`
    loaded. Reversible via `restore_incident`. Caller commits + broadcasts."""
    inc.ended_at = when
    inc.ended_reason = "dismissed"
    for t in inc.threats:
        if t.closed_at is None:
            close_track(t, when, "dismissed")
    log.info("incident %s dismissed (admin)", inc.id)


def restore_incident(inc: Incident) -> None:
    """Undo `dismiss_incident`: reopen the incident and only the tracks it
    dismissed (never touches tracks closed for a real reason)."""
    inc.ended_at = None
    inc.ended_reason = None
    for t in inc.threats:
        if t.closed_reason == "dismissed":
            reopen_track(t)
    log.info("incident %s restored (admin)", inc.id)


async def end_active_incidents(session, when: datetime, ended_reason: str) -> list[Incident]:
    """End every open incident — used on a full all-clear (`ended_reason=
    'all_clear'`, spotter "Відбій тривоги") or the official alert ending
    (`ended_reason='alert_end'`) — see ingest.py's two callers."""
    incs = list(await session.scalars(select(Incident).where(Incident.ended_at.is_(None))))
    for inc in incs:
        inc.ended_at = when
        inc.ended_reason = ended_reason
        log.info("incident %s ended (reason=%s)", inc.id, ended_reason)
    if incs:
        await session.commit()
    return incs


async def end_incidents_without_open_tracks(
    session, when: datetime, ended_reason: str
) -> list[Incident]:
    """End active incidents whose member tracks are ALL closed — used after a
    type-scoped clear ("Відбій балістичної загрози") or a "дорозвідка"
    stand-down: an explicit spotter stand-down signal PLUS nothing left flying
    means the attack is over. Distinct from end_active_incidents (which a
    spotter can't trigger — a full відбій is alert-channel-only): an incident
    that still has an open track of another type stays active."""
    incs = list(await session.scalars(
        select(Incident)
        .where(Incident.ended_at.is_(None))
        .options(selectinload(Incident.threats))
    ))
    ended = []
    for inc in incs:
        if inc.threats and all(t.closed_at is not None for t in inc.threats):
            inc.ended_at = when
            inc.ended_reason = ended_reason
            log.info("incident %s ended (reason=%s, no open tracks left)", inc.id, ended_reason)
            ended.append(inc)
    if ended:
        await session.commit()
    return ended


async def close_stale_incidents(session, now: datetime, minutes: int) -> list[Incident]:
    """End incidents whose last member activity is older than `minutes` — an
    attack that quietly petered out without an explicit all-clear."""
    stale_gap = timedelta(minutes=minutes)
    incs = list(await session.scalars(select(Incident).where(Incident.ended_at.is_(None))))
    ended = []
    for inc in incs:
        if not _within(inc.last_activity_at, now, stale_gap):
            inc.ended_at = now
            inc.ended_reason = "stale"
            log.info("incident %s ended (reason=stale)", inc.id)
            ended.append(inc)
    if ended:
        await session.commit()
    return ended

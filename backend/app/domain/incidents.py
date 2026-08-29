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

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ..config import settings
from ..models import Alert, Incident, Threat, ThreatEvent
from ..timeutil import naive, within
from .lifecycle import close_track, reopen_track

log = logging.getLogger("incidents")

# Target-type severity — an incident is labelled by its most dangerous member.
# `fpv` sits BELOW shahed: it is the least consequential thing on this list per
# target — one quadcopter, one building — even though it is the most frequent.
# `kab` sits between the drones and the cruise missile: a heavier warhead than
# any drone, but it lands near the border and never crosses the country.
_SEVERITY = {"unknown": 0, "fpv": 1, "shahed": 2, "jet_drone": 3,
             "kab": 4, "missile": 5, "ballistic": 6}

# Types that mean "the same kind of thing is flying" for inference purposes.
# missile/ballistic is already treated as one family by target_types.upgrade_type.
_FAMILY = {"shahed": "drone", "jet_drone": "drone", "fpv": "drone",
           "missile": "missile", "ballistic": "missile", "kab": "kab"}


async def incident_type_prior(session, inc: Incident, when: datetime) -> str | None:
    """Type an untyped sighting may inherit, or None when the incident can't say.

    NOT `inc.target_type`/`inc.attack_types` — those are max-severity labels
    that only ratchet up, so one Циркон track made every later untyped callout
    ballistic (08-04: the Бровари drone corridor read as балістика, losing its
    vector too). Only honest while the raid is one family; combined -> unknown.

    And they never forget, which is the same bug one phase later: a raid that
    OPENED with a ballistic salvo went on labelling cruise callouts «балістика»
    an hour after that salvo ended, while every spotter in the feed was saying
    «Калібр» — 20 of them in the nine minutes from 22:27 (live 2026-08-19).
    Telling an operator "ballistic" buys them a minute of reaction time when a
    Kalibr was giving them ten, so the prior is read from the tracks that are
    actually FLYING: incident members whose last sighting is still inside the
    stale window. A phase that is over stops speaking for the one running now.
    """
    fresh = await _recent_member_types(session, inc, when)
    families = {_FAMILY.get(t) for t in fresh}
    if len(families) != 1 or None in families:
        return None
    return max(fresh, key=lambda t: _SEVERITY.get(t, 0))


async def _recent_member_types(session, inc: Incident, when: datetime) -> set[str]:
    """Target types of this incident's tracks sighted within the stale window of
    `when`. Dismissed tracks are excluded, same as recompute_incident_types."""
    gap = timedelta(minutes=settings.track_stale_minutes)
    stmt = (
        select(Threat.target_type, func.max(ThreatEvent.event_time))
        .join(ThreatEvent, ThreatEvent.threat_id == Threat.id)
        .where(
            Threat.incident_id == inc.id,
            Threat.target_type.not_in(("unknown",)),
            Threat.closed_reason.is_distinct_from("dismissed"),
        )
        .group_by(Threat.id, Threat.target_type)
    )
    return {
        target_type
        for target_type, last_seen in (await session.execute(stmt)).all()
        if last_seen is not None and within(last_seen, when, gap)
    }


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




async def find_active_incident(session, when: datetime) -> Incident | None:
    """The current open incident, if it saw activity within the gap window."""
    gap = timedelta(minutes=settings.incident_gap_minutes)
    stmt = (
        select(Incident)
        .where(Incident.ended_at.is_(None))
        .order_by(Incident.started_at.desc())
    )
    for inc in await session.scalars(stmt):
        if within(inc.last_activity_at, when, gap):
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
    inc.last_activity_at = max(inc.last_activity_at, when, key=naive)
    await session.commit()
    # Rebuild target_type/attack_types from the CURRENT members instead of
    # appending — so a track that upgraded its type mid-flight (missile ->
    # ballistic, see target_types.upgrade_type) leaves ONE type, not both, and the
    # incident no longer reads as a false 'combined' (the WORKFLOW.md /
    # attack.py::classify known compromise).
    await session.refresh(inc, ["threats"])
    recompute_incident_types(inc)
    await session.commit()
    return inc




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
    attack that quietly petered out without an explicit all-clear.

    Ends it at the instant it WENT stale (last activity + the window), not at
    the sweeper's wall clock. Those are the same thing to within one tick while
    the process is up, and wildly different when it wasn't: incident 200 ran
    18:38–18:49 on 2026-08-20, the backend was down overnight, and the first
    sweep at 16:56 the next day stamped `ended_at` there — the feed card read
    «Атака дронів · тривалість 22 год 18 хв» for an eleven-minute attack, and
    the journal counted the same 22 hours."""
    stale_gap = timedelta(minutes=minutes)
    incs = list(await session.scalars(select(Incident).where(Incident.ended_at.is_(None))))
    ended = []
    for inc in incs:
        if not within(inc.last_activity_at, now, stale_gap):
            # naive() for the same reason close_stale_tracks does it: this
            # column used to hold the aware `utcnow()`, and last_activity_at is
            # aware or naive depending on whether the row came from the DB.
            inc.ended_at = naive(inc.last_activity_at) + stale_gap
            inc.ended_reason = "stale"
            log.info("incident %s ended (reason=stale)", inc.id)
            ended.append(inc)
    if ended:
        await session.commit()
    return ended

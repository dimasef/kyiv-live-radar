"""Domain logic for admin-managed feed sources (Telegram channels).

Kept out of the route handlers so the add/reactivate rules are unit-testable and
the routes stay thin (same split as domain/corrections.py). The live listener
reads `is_active` sources from here; see feeds/telegram.py::_active_source_specs.
"""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Incident, Notice, RawMessage, Source, Threat, ThreatEvent
from .fusion import compute_fusion
from .incidents import recompute_incident_types


def normalize_ref(ref: str) -> str:
    """A channel handle as the listener resolves it: no leading @, trimmed."""
    return ref.strip().lstrip("@")


async def upsert_source(
    session: AsyncSession,
    *,
    subscribe_ref: str,
    name: str | None,
    role: str,
    region: str,
    trust_weight: float | None,
    user_id: int | None,
) -> Source:
    """Add a channel, or reactivate/refresh an existing row with the same handle.

    Re-adding a channel that was previously removed (removal = is_active=False,
    the row stays for its history/FKs) just flips it back on instead of colliding
    on the unique channel_key. Match is by subscribe_ref OR channel_key so both a
    listener-created row (channel_key=username, subscribe_ref NULL) and an
    admin-created one reconcile to the same source."""
    ref = normalize_ref(subscribe_ref)
    existing = (
        await session.scalars(
            select(Source).where(
                (Source.subscribe_ref == ref) | (Source.channel_key == ref)
            )
        )
    ).first()
    if existing is not None:
        existing.is_active = True
        existing.role = role
        existing.region = region
        existing.subscribe_ref = ref
        if name:
            existing.name = name
        if trust_weight is not None:
            existing.trust_weight = trust_weight
        existing.last_listener_error = None
        return existing

    src = Source(
        channel_key=ref,
        subscribe_ref=ref,
        name=(name or ref),
        role=role,
        region=region,
        trust_weight=trust_weight if trust_weight is not None else 1.0,
        is_active=True,
        added_by_user_id=user_id,
    )
    session.add(src)
    await session.flush()
    return src


async def delete_source_cascade(session: AsyncSession, source_id: int) -> dict | None:
    """HARD-delete a channel and ALL of its stored data — raw_messages, notices,
    and threat_events — then repair the track graph it touched. Irreversible
    (unlike deactivate, which keeps the row + history). Returns a count summary,
    or None if the source doesn't exist.

    Track repair after removing this source's events: a track left with no events
    is deleted; one still holding other sources' events keeps them and has its
    fusion recomputed. An incident (attack) left with no member tracks is deleted;
    otherwise its target types are recomputed from what remains."""
    src = await session.get(Source, source_id)
    if src is None:
        return None
    name = src.name

    affected_threat_ids = set(
        await session.scalars(
            select(ThreatEvent.threat_id).where(ThreatEvent.source_id == source_id)
        )
    )
    counts = {
        "events": await session.scalar(
            select(func.count()).select_from(ThreatEvent).where(ThreatEvent.source_id == source_id)
        ) or 0,
        "notices": await session.scalar(
            select(func.count()).select_from(Notice).where(Notice.source_id == source_id)
        ) or 0,
        "raw_messages": await session.scalar(
            select(func.count()).select_from(RawMessage).where(RawMessage.source_id == source_id)
        ) or 0,
    }

    await session.execute(delete(ThreatEvent).where(ThreatEvent.source_id == source_id))
    await session.execute(delete(Notice).where(Notice.source_id == source_id))
    await session.execute(delete(RawMessage).where(RawMessage.source_id == source_id))
    await session.flush()

    affected_incident_ids: set[int] = set()
    threats_deleted = 0
    for tid in affected_threat_ids:
        threat = await session.get(Threat, tid)
        if threat is None:
            continue
        await session.refresh(threat, ["events"])  # reflect the bulk event delete
        if threat.incident_id is not None:
            affected_incident_ids.add(threat.incident_id)
        if not threat.events:
            await session.delete(threat)
            threats_deleted += 1
        else:
            r = compute_fusion(threat.events)
            threat.corroboration_count = r.corroboration_count
            threat.has_conflict = r.has_conflict
            threat.confidence = r.confidence
    await session.flush()

    incidents_deleted = 0
    for iid in affected_incident_ids:
        inc = await session.get(Incident, iid)
        if inc is None:
            continue
        await session.refresh(inc, ["threats"])
        if not inc.threats:
            await session.delete(inc)
            incidents_deleted += 1
        else:
            recompute_incident_types(inc)

    await session.delete(src)
    await session.commit()
    return {
        "name": name,
        **counts,
        "threats_deleted": threats_deleted,
        "incidents_deleted": incidents_deleted,
    }

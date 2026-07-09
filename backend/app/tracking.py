"""Track builder: group structured events into target tracks (spec §5.4).

Grouping rule (in priority order):
1. Reply-threading — a message replying to a previous OPEN post joins that post's
   track (`find_track_by_reply`); the reply chain resolves transitively.
2. Corroboration — otherwise a sighting continues an open track only if it was
   recently seen over the SAME district (`find_corroborating_track`, within
   `corroboration_window_minutes`). This is a same-target MERGE between reports.
3. Otherwise it starts a NEW track.

We deliberately do NOT "continue the newest open track" for non-threaded
messages: that collapsed many independent targets from prose/point channels into
one giant zigzag during busy alerts.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .config import settings
from .fusion import compute_fusion
from .models import Threat, ThreatEvent


async def find_track_by_reply(
    session, source_id: int | None, reply_to_message_id: int | None
) -> Threat | None:
    """The open track a reply belongs to, via its parent message's event.

    Telegram reply ids are scoped to a channel, so we match on (source_id,
    source_message_id). The parent was itself already grouped onto the correct
    track, so resolving one hop gives the whole reply chain transitively. Returns
    None when there's no reply, no matching parent event, or the parent's track is
    already closed (a reply to a destroyed/lost target starts fresh via fallback).
    """
    if not settings.reply_grouping_enabled or source_id is None or reply_to_message_id is None:
        return None
    stmt = (
        select(Threat)
        .join(ThreatEvent, ThreatEvent.threat_id == Threat.id)
        .where(
            Threat.closed_at.is_(None),
            ThreatEvent.source_id == source_id,
            ThreatEvent.source_message_id == reply_to_message_id,
        )
        .options(selectinload(Threat.events))
        .order_by(Threat.created_at.desc())
    )
    return (await session.scalars(stmt)).first()


async def find_corroborating_track(
    session, when: datetime, district_ids: set[int]
) -> Threat | None:
    """Newest open track recently seen over one of `district_ids`.

    "Recently" = within `corroboration_window_minutes`. This is how a non-threaded
    report (prose/point channel with no reply) merges onto an existing target:
    only when it names a district that track was just over — otherwise it's
    treated as its own target. Never merges on recency alone.
    """
    if not district_ids:
        return None
    window = timedelta(minutes=settings.corroboration_window_minutes)
    stmt = (
        select(Threat)
        .where(Threat.closed_at.is_(None))
        .options(selectinload(Threat.events))
        .order_by(Threat.created_at.desc())
    )
    for threat in await session.scalars(stmt):  # newest-first
        for e in threat.events:
            if e.district_id in district_ids and _within(e.event_time, when, window):
                return threat
    return None


async def find_open_track(
    session, when: datetime, prefer_districts: set[int] | None = None
) -> Threat | None:
    """Open track whose last sighting is within the gap window.

    With `prefer_districts`, a track that has recently been seen over one of those
    districts wins over a merely-newer track — so e.g. "збито над X" closes the
    track that was actually over X, not whatever opened most recently.
    """
    stmt = (
        select(Threat)
        .where(Threat.closed_at.is_(None))
        .options(selectinload(Threat.events))
        .order_by(Threat.created_at.desc())
    )
    gap = timedelta(minutes=settings.track_gap_minutes)
    candidates = []
    for threat in await session.scalars(stmt):
        last = threat.events[-1].event_time if threat.events else threat.created_at
        if _within(last, when, gap):
            candidates.append(threat)
    if not candidates:
        return None
    if prefer_districts:
        for threat in candidates:  # newest-first order preserved
            if any(e.district_id in prefer_districts for e in threat.events):
                return threat
    return candidates[0]


def _within(a: datetime, b: datetime, gap: timedelta) -> bool:
    # Tolerate naive/aware mismatch from SQLite by comparing on replaced tzinfo.
    if a.tzinfo is None and b.tzinfo is not None:
        b = b.replace(tzinfo=None)
    elif a.tzinfo is not None and b.tzinfo is None:
        a = a.replace(tzinfo=None)
    return abs((b - a).total_seconds()) <= gap.total_seconds()


async def close_all_active(session, when: datetime) -> list[Threat]:
    """All-clear: close every open track."""
    stmt = select(Threat).where(Threat.closed_at.is_(None)).options(
        selectinload(Threat.events)
    )
    closed = list(await session.scalars(stmt))
    for t in closed:
        t.status = "lost"
        t.closed_at = when
    await session.commit()
    return closed


async def close_stale_tracks(session, now: datetime, minutes: int) -> list[Threat]:
    """Close open tracks with no sighting for `minutes` — a target that just went
    silent (no explicit destroyed/clear) must not linger as 'active' forever."""
    stmt = select(Threat).where(Threat.closed_at.is_(None)).options(
        selectinload(Threat.events)
    )
    stale_gap = timedelta(minutes=minutes)
    stale = []
    for t in await session.scalars(stmt):
        last = t.events[-1].event_time if t.events else t.created_at
        if not _within(last, now, stale_gap):
            t.status = "lost"
            t.closed_at = now
            stale.append(t)
    if stale:
        await session.commit()
    return stale


async def apply_fusion(session, threat: Threat) -> None:
    """Recompute derived multi-source signals from the track's events."""
    await session.refresh(threat, ["events"])
    r = compute_fusion(threat.events)
    threat.corroboration_count = r.corroboration_count
    threat.has_conflict = r.has_conflict
    threat.confidence = r.confidence
    await session.commit()
    await session.refresh(threat, ["events"])

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

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..config import settings
from ..models import Threat, ThreatEvent
from .fusion import compute_fusion
from .lifecycle import close_track

log = logging.getLogger("tracking")


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
    session, when: datetime, district_ids: set[int], as_of: datetime | None = None
) -> Threat | None:
    """Newest open track whose MOST RECENT sighting was over one of `district_ids`.

    "Recently" = within `corroboration_window_minutes`. This is how a non-threaded
    report (prose/point channel with no reply) merges onto an existing target:
    only when it names a district that track's CURRENT (latest) position was
    over — not any district it passed through earlier. Matching against the
    full history let a track's match surface grow with every event it absorbed,
    snowballing into false merges with unrelated LATER targets that happened to
    pass through the same busy corridor district (Бровари, Троєщина, the
    Славутич/Десна/Троя entry corridor...) within the window during a busy
    multi-wave night — confirmed empirically via eval/track_eval.py against a
    real backfill (mega-track-lite: a track absorbing 5-7 genuinely distinct
    missiles/drones that all happened to transit the same chokepoint district
    minutes apart). Never merges on recency alone.

    `as_of` (set only for an async-triage RESCUE at its original timestamp)
    evaluates each track's "latest" position among events at or before that
    instant — so a rescue joins the track it actually corroborated at T0, not
    one that has since moved on to a different district. The live path passes
    None (full history, behavior byte-identical — proven by track_eval).
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
        events = threat.events
        if as_of is not None:
            events = [e for e in events if not _after(e.event_time, as_of)]
        if not events:
            continue
        latest_time = max(e.event_time for e in events)
        if not _within(latest_time, when, window):
            continue
        latest_districts = {e.district_id for e in events if e.event_time == latest_time}
        if latest_districts & district_ids:
            return threat
    return None


def _after(a: datetime, b: datetime) -> bool:
    """a > b, tolerating naive/aware mismatch (all values are UTC)."""
    an = a.replace(tzinfo=None) if a.tzinfo is not None else a
    bn = b.replace(tzinfo=None) if b.tzinfo is not None else b
    return an > bn


async def find_open_track(
    session,
    when: datetime,
    prefer_districts: set[int] | None = None,
    gap_minutes: int | None = None,
) -> Threat | None:
    """Open track whose last sighting is within the gap window.

    With `prefer_districts`, a track that has recently been seen over one of those
    districts wins over a merely-newer track — so e.g. "збито над X" closes the
    track that was actually over X, not whatever opened most recently.

    `gap_minutes` defaults to `track_gap_minutes` (grouping a new sighting onto
    the same track); a closing message (destroyed) should instead look as far
    back as a track can go before it's considered stale (`track_stale_minutes`)
    — otherwise a reply-less "знищено" landing 16-19 minutes after the last
    sighting (past the 15-minute grouping gap but within the 20-minute stale
    window) would find no track to close, even though the sweeper hasn't
    closed it yet either.
    """
    stmt = (
        select(Threat)
        .where(Threat.closed_at.is_(None))
        .options(selectinload(Threat.events))
        .order_by(Threat.created_at.desc())
    )
    gap = timedelta(minutes=gap_minutes if gap_minutes is not None else settings.track_gap_minutes)
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


async def find_recent_impact(session, district_id: int, when: datetime) -> Threat | None:
    """A recent impact marker over the SAME district (within impact_dedup_minutes).

    Two sources reporting one strike ("влучання" + "пошкоджено будівлю") over the
    same raion minutes apart are the SAME hit — the second should corroborate the
    first marker, not stack a second pin on the identical point. Impact markers
    are closed-on-creation, so this deliberately looks past closed_at.
    """
    window = timedelta(minutes=settings.impact_dedup_minutes)
    stmt = (
        select(Threat)
        .where(Threat.status == "impact")
        .options(selectinload(Threat.events))
        .order_by(Threat.created_at.desc())
    )
    for threat in await session.scalars(stmt):
        if not threat.events:
            continue
        latest = max(e.event_time for e in threat.events)
        if not _within(latest, when, window):
            continue
        if any(e.district_id == district_id for e in threat.events):
            return threat
    return None


async def find_open_citywide(session, when: datetime) -> Threat | None:
    """The current open city-wide alert (scope='city'), if one is still fresh.

    Repeated "ціль на місто" callouts during one attack should feed ONE
    city-level alert, not spawn a new one each time — so a citywide message
    continues an open city-wide threat whose last event is within the track-gap
    window, else it starts a fresh one. City-wide events live on the sentinel
    district, which no normal sighting ever matches, so this never collides with
    per-district tracks.
    """
    stmt = (
        select(Threat)
        .where(Threat.closed_at.is_(None), Threat.scope == "city")
        .options(selectinload(Threat.events))
        .order_by(Threat.created_at.desc())
    )
    gap = timedelta(minutes=settings.track_gap_minutes)
    for threat in await session.scalars(stmt):
        last = threat.events[-1].event_time if threat.events else threat.created_at
        if _within(last, when, gap):
            return threat
    return None


def _within(a: datetime, b: datetime, gap: timedelta) -> bool:
    # Tolerate naive/aware mismatch from SQLite by comparing on replaced tzinfo.
    if a.tzinfo is None and b.tzinfo is not None:
        b = b.replace(tzinfo=None)
    elif a.tzinfo is not None and b.tzinfo is None:
        a = a.replace(tzinfo=None)
    return abs((b - a).total_seconds()) <= gap.total_seconds()


async def close_all_active(
    session, when: datetime, reason: str, target_type: str | None = None
) -> list[Threat]:
    """Close every open track — or, with `target_type`, only open tracks of
    that type. Used both for a full all-clear ("відбій", `reason='all_clear'`)
    and for a scoped "дорозвідка" stand-down (`reason='stand_down'`, ППО lost
    tracking for one target type)."""
    stmt = select(Threat).where(Threat.closed_at.is_(None)).options(
        selectinload(Threat.events)
    )
    if target_type is not None:
        stmt = stmt.where(Threat.target_type == target_type)
    closed = list(await session.scalars(stmt))
    for t in closed:
        close_track(t, when, reason)
    await session.commit()
    return closed


async def close_stale_tracks(
    session, now: datetime, minutes: int, ballistic_minutes: int | None = None
) -> list[Threat]:
    """Close open tracks with no sighting for `minutes` — a target that just went
    silent (no explicit destroyed/clear) must not linger as 'active' forever.

    `ballistic_minutes` (when set) is a SHORTER window for a district-scoped
    ballistic dot: sub-minute flight means such a track hangs on the map long
    after impact. A scope='city' ballistic alert (the barrage banner) keeps the
    normal window — its waves can lull for minutes."""
    stmt = select(Threat).where(Threat.closed_at.is_(None)).options(
        selectinload(Threat.events)
    )
    stale = []
    for t in await session.scalars(stmt):
        gap_min = minutes
        if ballistic_minutes is not None and t.target_type == "ballistic" and t.scope != "city":
            gap_min = ballistic_minutes
        last = t.events[-1].event_time if t.events else t.created_at
        if not _within(last, now, timedelta(minutes=gap_min)):
            close_track(t, now, "stale")
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
    log.debug("track %s fusion: corroboration=%d confidence=%.2f",
             threat.id, r.corroboration_count, r.confidence)
    if r.has_conflict:
        log.warning("track %s fusion conflict: sources disagree on target type", threat.id)

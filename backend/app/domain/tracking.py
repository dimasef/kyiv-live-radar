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

Every lookup here is REGION-scoped (see models.REGIONS). Tracks in different
regions are separate populations that never corroborate, continue or close each
other — without that, `find_open_track`'s "newest open track" fallback would
attach a northern «збито» to whatever Kyiv track opened last, and one channel's
«Відбій» would close both regions at once.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..config import settings
from ..models import HOME_REGION, Threat, ThreatEvent
from ..timeutil import naive, within
from .fusion import FusionResult, compute_fusion
from .lifecycle import close_track
from .staleness import is_reply_tracked, last_event_at, stale_window_minutes

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
    session, when: datetime, district_ids: set[int], as_of: datetime | None = None,
    *, region: str = HOME_REGION,
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
        .where(Threat.closed_at.is_(None), Threat.region == region)
        .options(selectinload(Threat.events))
        .order_by(Threat.created_at.desc())
    )
    for threat in await session.scalars(stmt):  # newest-first
        events = threat.events
        if as_of is not None:
            events = [e for e in events if naive(e.event_time) <= naive(as_of)]
        if not events:
            continue
        latest_time = max(naive(e.event_time) for e in events)
        if not within(latest_time, when, window):
            continue
        latest_districts = {e.district_id for e in events if naive(e.event_time) == latest_time}
        if latest_districts & district_ids:
            return threat
    return None




async def find_stood_down_track(
    session, when: datetime, district_ids: set[int], *, region: str = HOME_REGION
) -> Threat | None:
    """Newest track closed by a stand-down within the grace window whose latest
    sighting was over one of `district_ids` — the district-track twin of
    `find_stood_down_citywide`. A «Чисто!»/«Дорозвідка» between callouts of the
    SAME still-flying target must not split its session in two: the follow-up
    callout reopens the stood-down track instead of starting a fresh one."""
    if not district_ids:
        return None
    grace = timedelta(minutes=settings.standdown_grace_minutes)
    stmt = (
        select(Threat)
        .where(Threat.closed_reason == "stand_down", Threat.scope != "city",
               Threat.region == region)
        .options(selectinload(Threat.events))
        .order_by(Threat.closed_at.desc())
    )
    for threat in await session.scalars(stmt):  # most recently closed first
        if threat.closed_at is None or not within(threat.closed_at, when, grace):
            break  # ordered by closed_at — everything after is older still
        if not threat.events:
            continue
        latest_time = max(naive(e.event_time) for e in threat.events)
        latest_districts = {
            e.district_id for e in threat.events if naive(e.event_time) == latest_time
        }
        if latest_districts & district_ids:
            return threat
    return None


async def find_stale_closed_track(
    session, when: datetime, district_ids: set[int], *, region: str = HOME_REGION
) -> Threat | None:
    """Newest track the SWEEPER retired as silent whose latest sighting was over
    one of `district_ids` — the track a late «збито» is talking about.

    Since the stale windows became per-type (domain/staleness.py), a target can
    be swept off the map minutes before the channel reports it shot down. The
    caller relabels such a close rather than reopening the track: the map is
    already right, only the REASON is wrong.

    Reach is `track_stale_minutes`, the same lookback `find_open_track` gets for
    a closing message — so this recovers exactly what the shorter windows took
    away, and never reaches further back than the old single window did.

    Matches on the LATEST sighting's district only, like `find_stood_down_track`:
    a busy corridor district (Бровари, Троєщина) appears in half the tracks of a
    given night, and matching any event would relabel whichever one happened to
    transit it first."""
    if not district_ids:
        return None
    reach = timedelta(minutes=settings.track_stale_minutes)
    stmt = (
        select(Threat)
        .where(Threat.closed_reason == "stale", Threat.scope != "city",
               Threat.region == region)
        .options(selectinload(Threat.events))
        .order_by(Threat.closed_at.desc())
    )
    for threat in await session.scalars(stmt):  # most recently closed first
        if threat.closed_at is None or not within(threat.closed_at, when, reach):
            break  # ordered by closed_at — everything after is older still
        if not threat.events:
            continue
        latest_time = max(naive(e.event_time) for e in threat.events)
        if not within(latest_time, when, reach):
            continue
        latest_districts = {
            e.district_id for e in threat.events if naive(e.event_time) == latest_time
        }
        if latest_districts & district_ids:
            return threat
    return None


async def find_open_track(
    session,
    when: datetime,
    prefer_districts: set[int] | None = None,
    gap_minutes: int | None = None,
    *,
    region: str = HOME_REGION,
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

    The `region` scope matters most here: this is the one lookup that falls back
    to "the newest open track" when nothing matches `prefer_districts`, so
    without it a district-less «збито» from a northern channel would close an
    unrelated Kyiv track.
    """
    stmt = (
        select(Threat)
        .where(Threat.closed_at.is_(None), Threat.region == region)
        .options(selectinload(Threat.events))
        .order_by(Threat.created_at.desc())
    )
    gap = timedelta(minutes=gap_minutes if gap_minutes is not None else settings.track_gap_minutes)
    candidates = []
    for threat in await session.scalars(stmt):
        last = threat.events[-1].event_time if threat.events else threat.created_at
        if within(last, when, gap):
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
    # Bounded in SQL, not in Python. Unfiltered, this re-read every impact ever
    # recorded — with all their events — once PER NAMED DISTRICT of every
    # incoming impact message. `created_at` is when the marker was made, so a
    # candidate outside the dedup window cannot have an event inside it; the
    # extra window of slack keeps the check on `event_time` authoritative.
    cutoff = naive(when) - 2 * window
    stmt = (
        select(Threat)
        .where(Threat.status == "impact", Threat.created_at >= cutoff)
        .options(selectinload(Threat.events))
        .order_by(Threat.created_at.desc())
    )
    for threat in await session.scalars(stmt):
        if not threat.events:
            continue
        latest = max(naive(e.event_time) for e in threat.events)
        if not within(latest, when, window):
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
        if within(last, when, gap):
            return threat
    return None


async def find_stood_down_citywide(session, when: datetime) -> Threat | None:
    """The most recent city-wide alert closed by a stand-down within the grace
    window — «Чисто!»/«Дорозвідка» between waves of one salvo must not leave
    the very next pulse or "на Київ" callout with nothing to continue. Only a
    stand-down qualifies: an official all-clear ("відбій") is final."""
    stmt = (
        select(Threat)
        .where(Threat.scope == "city", Threat.closed_reason == "stand_down")
        .options(selectinload(Threat.events))
        .order_by(Threat.closed_at.desc())
        .limit(1)
    )
    threat = await session.scalar(stmt)
    grace = timedelta(minutes=settings.standdown_grace_minutes)
    if threat is not None and threat.closed_at is not None and within(threat.closed_at, when, grace):
        return threat
    return None




async def close_all_active(
    session, when: datetime, reason: str, target_type: str | None = None,
    *, region: str = HOME_REGION,
) -> list[Threat]:
    """Close every open track IN `region` — or, with `target_type`, only open
    tracks of that type. Used both for a full all-clear ("відбій",
    `reason='all_clear'`) and for a scoped "дорозвідка" stand-down
    (`reason='stand_down'`, ППО lost tracking for one target type).

    An all-clear is always regional: sirens end per oblast, and a northern
    channel's «Чисто!» says nothing about what is still flying over Kyiv."""
    stmt = select(Threat).where(
        Threat.closed_at.is_(None), Threat.region == region
    ).options(
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
    session,
    now: datetime,
    *,
    orphan_windows: dict[str, int] | None = None,
    tracked_windows: dict[str, int] | None = None,
    default_minutes: int | None = None,
    region: str | None = None,
) -> list[Threat]:
    """Close open tracks that have gone silent past their window — a target that
    just stopped being reported (no explicit destroyed/clear) must not linger as
    'active' forever.

    The window itself and the "last seen" rule live in domain/staleness.py: it
    depends on the target type AND on whether the track has a resolved reply
    chain. The API publishes the same instant as `stale_at`, so the map's
    fade-out lands exactly on this close.

    `region=None` (the sweeper) sweeps every region: staleness is a property of
    the individual track, not of its pool."""
    orphan = orphan_windows if orphan_windows is not None else settings.stale_minutes_orphan
    tracked = tracked_windows if tracked_windows is not None else settings.stale_minutes_tracked
    fallback = default_minutes if default_minutes is not None else settings.track_stale_minutes
    stmt = select(Threat).where(Threat.closed_at.is_(None)).options(
        selectinload(Threat.events)
    )
    if region is not None:
        stmt = stmt.where(Threat.region == region)
    stale = []
    for t in await session.scalars(stmt):
        gap_min = stale_window_minutes(
            t.target_type,
            t.scope,
            tracked=is_reply_tracked(t),
            orphan_windows=orphan,
            tracked_windows=tracked,
            default_minutes=fallback,
        )
        last = last_event_at(t)
        if not within(last, now, timedelta(minutes=gap_min)):
            # Closed at the instant it WENT stale, not at the sweeper's wall
            # clock — the same instant `stale_at` already publishes for the
            # map's fade, so the two finally agree. Within one tick of `now`
            # while the process is up; hours off after any downtime, which is
            # how a 2026-08-20 track came to be stamped closed the next
            # afternoon and inflated its incident's duration to 22 hours.
            #
            # `naive()` first: `last` is an event time, which comes back naive
            # from SQLite but is aware when the event was added in this same
            # session — storing whichever we happened to get would make
            # closed_at compare-unsafe against the aware `utcnow()` it used to
            # be. Everything here is UTC wall-clock either way.
            close_track(t, naive(last) + timedelta(minutes=gap_min), "stale")
            stale.append(t)
    if stale:
        await session.commit()
    return stale


def set_fusion(threat: Threat) -> FusionResult:
    """Recompute the derived multi-source signals onto the track, no I/O.

    Split out of `apply_fusion` for callers that already hold loaded events and
    commit on their own schedule (admin/moderation.py deletes a sighting inside
    one transaction) — the numbers must not survive the events they were derived
    from."""
    r = compute_fusion(threat.events)
    threat.corroboration_count = r.corroboration_count
    threat.has_conflict = r.has_conflict
    threat.confidence = r.confidence
    return r


async def apply_fusion(session, threat: Threat) -> None:
    """Recompute derived multi-source signals from the track's events.

    The refresh autoflushes the pending event and reloads the collection; the
    commit that follows does NOT expire it (the sessionmaker sets
    expire_on_commit=False), so a second refresh afterwards would just be a
    third round-trip for rows we already hold.
    """
    await session.refresh(threat, ["events"])
    r = set_fusion(threat)
    await session.commit()
    log.debug("track %s fusion: corroboration=%d confidence=%.2f",
             threat.id, r.corroboration_count, r.confidence)
    if r.has_conflict:
        log.warning("track %s fusion conflict: sources disagree on target type", threat.id)

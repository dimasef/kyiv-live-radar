"""Ingest pipeline: one raw message -> stored + parsed + tracked + broadcast.

Single entry point (`ingest_message`) shared by the Telethon listener and the
text simulator, so both exercise the exact same real parsing/tracking code.
`process_parsed` is the reusable inner half (parse -> track -> fuse) for an
already-stored raw message — also used by `scripts/reprocess_raw.py` to replay
history through an improved parser/gazetteer.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select

from ..domain.alerts import AlertSignal, apply_alert_signal
from ..domain.axes import AxisSignal, apply_axis_signal, refresh_open_axis
from ..domain.districts import citywide_district_id
from ..domain.origins import target_elsewhere
from ..domain.incidents import (
    attach_to_incident,
    end_active_incidents,
    end_incidents_without_open_tracks,
    find_active_incident,
)
from ..domain.lifecycle import close_track, promote_track, reopen_track
from ..domain.tracking import (
    apply_fusion,
    close_all_active,
    find_corroborating_track,
    find_open_citywide,
    find_open_track,
    find_recent_impact,
    find_stood_down_citywide,
    find_stood_down_track,
    find_track_by_reply,
)
from ..config import settings
from ..observability import ingest_span, metrics
from ..models import Notice, RawMessage, Threat, ThreatEvent
from ..parsing import DistrictHit, DistrictMatcher, LlmUsage, ParseResult, normalize, parse_message
from ..parsing.alert_parser import parse_alert_message
from .results import Broadcast

log = logging.getLogger("tracking")

# Serialize ingestion: concurrent inbound messages sharing one open track would
# otherwise race (split tracks, wrong corroboration, SQLite "database is locked").
# Single-instance MVP — one lock is enough; multi-instance would move to the DB.
_ingest_lock = asyncio.Lock()

# Per-source "last stated target type" context for cross-message type
# inheritance (see settings.type_inherit_window_minutes). Keyed by source_id ->
# (target_type, when). In-memory and order-dependent, which is fine: ingestion
# is serialized and every feed path (live, replay, reprocess) presents messages
# in chronological order per source. A process restart simply drops the context
# (a district event right after a restart falls back to "unknown" — harmless).
# Rule-only: mutating an already-districted message's type never adds an LLM
# call, since should_fallback short-circuits to False whenever districts exist.
_recent_type: dict[int, tuple[str, datetime]] = {}


def _note_and_inherit_type(parsed: ParseResult, source_id: int | None, when: datetime) -> None:
    """Record this message's stated type, or inherit a recent one onto a
    district-bearing message that stated none. Mutates `parsed.target_type`."""
    if source_id is None:  # no channel identity (e.g. simulator) — no context
        return
    # Conversational/meta chatter mentions types without being about a live
    # target — a donation post's "до останнього Шахеда та ракети", a recap, a
    # quoted official — and on 07-18 such a mention poisoned a channel's
    # context mid-salvo. These classes neither record nor consume a type.
    if (parsed.promo or parsed.ad_action or parsed.political_quote
            or parsed.civic_notice or parsed.eppo_marks or parsed.siren_only
            or parsed.negated or parsed.summary or parsed.day_recap):
        return
    if parsed.target_type != "unknown":
        # "missile" is the generic parent of the specific "ballistic": during a
        # ballistic salvo a spotter often drops a bare "3 ракети" between the
        # toponym callouts, which must NOT downgrade a still-fresh ballistic
        # context to generic missile. Any OTHER type (shahed/jet, or ballistic
        # itself) is a real change and overwrites normally. Time is refreshed
        # either way so the ongoing attack keeps the context alive.
        prev = _recent_type.get(source_id)
        if (
            parsed.target_type == "missile"
            and prev is not None
            and prev[0] == "ballistic"
            and _within_inherit_window(when, prev[1])
        ):
            _recent_type[source_id] = ("ballistic", when)
        else:
            _recent_type[source_id] = (parsed.target_type, when)
        return
    # Untyped: inherit only when the message is a real (localizable or
    # city-wide) sighting — a bare "Троя" or "Ціль на місто!" between typed
    # posts — AND a recent stated type exists for this same channel.
    if not parsed.districts and not parsed.citywide:
        return
    recent = _recent_type.get(source_id)
    if recent is None:
        return
    rtype, rwhen = recent
    if _within_inherit_window(when, rwhen):
        parsed.target_type = rtype


def _within_inherit_window(a: datetime, b: datetime) -> bool:
    """Whether `a` and `b` are within the type-inheritance window. Drops tzinfo
    first so SQLite-naive and aware datetimes compare (all values are UTC)."""
    an = a.replace(tzinfo=None) if a.tzinfo is not None else a
    bn = b.replace(tzinfo=None) if b.tzinfo is not None else b
    window = timedelta(minutes=settings.type_inherit_window_minutes)
    return abs((an - bn).total_seconds()) <= window.total_seconds()


def _upgrade_type(current: str, new: str) -> str:
    """The target type a track should hold given a new event's stated type.

    Upgrade `unknown` to any stated type; and within the missile family upgrade
    the generic `missile` to the more specific, more severe `ballistic` (a bare
    "8 ракет" followed by "8 балістичних С-400" is the SAME salvo, better
    identified). Never cross families (a shahed track stays shahed even if a
    missile event lands — that genuine disagreement is surfaced as a conflict by
    fusion, not silently overwritten)."""
    if current == "unknown":
        return new
    if {current, new} == {"missile", "ballistic"}:
        return "ballistic"
    return current


def _threat_status_for(parsed: ParseResult) -> str:
    if parsed.status == "unconfirmed":
        return "unconfirmed"
    return "tracking"


def should_fallback(parsed: ParseResult) -> bool:
    """Route to the LLM only when rules couldn't localize a threat-flavored
    message — not for junk/news and not when rules already succeeded."""
    if parsed.aftermath:  # consequence/casualty news — not a live target
        return False
    if parsed.siren_only:  # technical "alarm is on here" echo — not a live target
        return False
    if parsed.negated:  # explicit denial ("не йде на...") — not a live target
        return False
    if parsed.civic_notice:  # transport/road city news — not a live target
        return False
    if parsed.eppo_marks:  # dismissed єППО app marks — not a live target
        return False
    if parsed.political_quote:  # official statement repost — not a live target
        return False
    if parsed.lost_signal:  # "дорозвідка" stand-down — handled directly by ingest, not a live target
        return False
    if parsed.citywide:  # city-level alert with no raion — LLM can't localize it further
        return False
    if parsed.directional:  # rules already raised a directional axis — no district to find
        return False
    if parsed.summary:  # retrospective recap, not a live target — nothing to localize
        return False
    if parsed.target_pulse:  # terse pulse, no place — nothing for the LLM to localize
        return False
    if parsed.districts or parsed.status in ("clear", "destroyed"):
        return False
    if target_elsewhere(normalize(parsed.raw_text)):
        return False
    return parsed.target_type != "unknown" or parsed.status in ("confirmed", "unconfirmed")


async def _resolve(
    text: str, matcher: DistrictMatcher
) -> tuple[ParseResult, str, bool, LlmUsage | None, dict | None]:
    """Rule-based first; LLM fallback only when warranted and configured. The
    3rd return value is whether the LLM was actually CALLED — distinct from
    decision_source=='llm' (which also requires the call to have recovered a
    district); a call that returned nothing still spent the API budget and is
    worth surfacing in /raw_messages. The 4th is its token usage/cost, set
    whenever the call actually completed. The 5th is the LLM's full structured
    response (district_ids + triage category/surface/summary), stored on the
    raw message for /raw audit regardless of whether its districts were used
    (see llm_extract)."""
    parsed = parse_message(text, matcher)
    if settings.llm_fallback_enabled and settings.anthropic_api_key and should_fallback(parsed):
        from .triage import llm_spend_ok

        # Shared cost guard: when the day/month LLM budget is exhausted, the
        # inline fallback degrades to rules-only too (not just the async engine).
        if not await llm_spend_ok():
            return parsed, "rule", False, None, None
        from ..parsing.llm import llm_extract

        llm, usage, response = await llm_extract(text, matcher)
        # Trust the LLM for LOCALIZATION only — use its result only when it
        # actually recovered a district. Never let it declare an all-clear /
        # destroyed on its own: rules own those via explicit keywords
        # ("відбій"/"збито"), and a keyword-detected stand-down never reaches the
        # LLM anyway (see should_fallback). Letting the LLM infer a clear from a
        # reassuring tone ("масованих пусків немає… відпочивайте") produced false
        # "Відбій" feed entries AND risked closing active tracks via close_all_active.
        # The triage fields (category/surface/summary) are stored via `response`
        # but NOT acted on yet — Stage 1 is collect-only.
        if llm is not None and llm.districts:
            return llm, "llm", True, usage, response
        return parsed, "rule", True, usage, response
    return parsed, "rule", False, None, None


async def ingest_message(session, **kwargs) -> list[Broadcast]:
    """Serialized entry point — see _ingest_locked for the pipeline."""
    async with _ingest_lock:
        return await _ingest_locked(session, **kwargs)


async def _ingest_locked(
    session,
    *,
    text: str,
    matcher: DistrictMatcher,
    when: datetime,
    source_id: int | None = None,
    message_id: int | None = None,
    forwarded_from_id: int | None = None,
    forwarded_from_channel_id: int | None = None,
    reply_to_message_id: int | None = None,
) -> list[Broadcast]:
    # 0. Idempotency guard: a real Telegram message_id is unique per channel.
    #    Re-ingesting one (repeated backfill on every restart was doing exactly
    #    this) must be a no-op, not a duplicate raw_message + duplicate events on
    #    a possibly-different track. Simulator messages (message_id=None) skip
    #    this check — they have no stable identity to dedupe on.
    if message_id is not None:
        dup = await session.scalar(
            select(RawMessage.id).where(
                RawMessage.source_id == source_id, RawMessage.message_id == message_id
            )
        )
        if dup is not None:
            return []

    # 1. Persist the raw message first (first-hand data, eval set, reprocessing).
    raw = RawMessage(
        source_id=source_id,
        message_id=message_id,
        text=text,
        event_time=when,
        forwarded_from_id=forwarded_from_id,
        forwarded_from_channel_id=forwarded_from_channel_id,
        reply_to_message_id=reply_to_message_id,
    )
    session.add(raw)
    await session.commit()

    return await process_parsed(
        session,
        raw=raw,
        text=text,
        matcher=matcher,
        when=when,
        source_id=source_id,
        message_id=message_id,
        forwarded_from_id=forwarded_from_id,
        forwarded_from_channel_id=forwarded_from_channel_id,
        reply_to_message_id=reply_to_message_id,
    )


@dataclass
class IngestContext:
    """Groups the parameters every process_parsed handler below needs — not a
    plugin framework, just avoids re-threading nine positional args through
    each handler signature."""

    session: object
    raw: RawMessage
    parsed: ParseResult
    decision_source: str
    when: datetime
    source_id: int | None
    message_id: int | None
    forwarded_from_id: int | None
    forwarded_from_channel_id: int | None
    reply_to_message_id: int | None
    # Set only for a RESCUED message (async triage re-injecting a suppressed
    # sighting): corroboration is then evaluated as-of this original time, not
    # "now", so the rescue joins the track it actually corroborated at T0 rather
    # than one that has since moved on. None on the live path (behavior unchanged).
    as_of: datetime | None = None
    # Operator-facing gist from an LLM verdict (inline-llm or rescued events) —
    # stamped onto each ThreatEvent this message creates, for the feed headline.
    # None for rule-only messages.
    llm_summary: str | None = None
    # True when parsed.target_type came from the open INCIDENT's dominant type
    # (second-tier fallback), not the message/channel itself. The ballistic
    # enumeration split must not trust it: on a mixed drone+ballistic night the
    # incident reads "ballistic" and would wrongly split a meandering drone's
    # «Троя/Воскресенка» enumeration.
    type_from_incident: bool = False

    async def done(self) -> None:
        self.raw.processed = True
        await self.session.commit()


def _axis_dedup_key(ctx: IngestContext) -> str:
    """Independent-source identity for axis corroboration (see
    fusion._origin_keys / triage._source_dedup_key)."""
    if ctx.forwarded_from_channel_id is not None:
        return f"orig:{ctx.forwarded_from_channel_id}"
    return f"src:{ctx.source_id}"


async def _raise_axis_from_parsed(ctx: IngestContext) -> Broadcast | None:
    """Raise/refresh a directional axis for a message that named an inbound
    origin (ctx.parsed.origin_key/_sector), whether it stood alone (directional)
    or accompanied a city/district sighting. No-op when no origin was named."""
    parsed = ctx.parsed
    if parsed.origin_sector is None:
        return None
    axis = await apply_axis_signal(ctx.session, AxisSignal(
        sector=parsed.origin_sector,
        target_type=parsed.target_type,
        when=ctx.when,
        origin_key=parsed.origin_key,
        source_dedup_key=_axis_dedup_key(ctx),
        raw_id=ctx.raw.id,
    ))
    return Broadcast("axis", axis=axis) if axis is not None else None


async def _handle_directional(ctx: IngestContext) -> list[Broadcast]:
    """Standalone directional/origin callout ("Загроза балістики з Брянська") —
    no Kyiv raion to localize. Raise a directional AXIS (a screen-edge wedge)
    and surface a rule-generated directional notice in the feed; never a track."""
    parsed, when = ctx.parsed, ctx.when
    notice = Notice(
        kind="directional", text=parsed.raw_text, target_type=parsed.target_type,
        source_id=ctx.source_id, event_time=when, source_message_id=ctx.message_id,
        origin=parsed.origin_key, generated_by="rule",
    )
    ctx.session.add(notice)
    await ctx.session.commit()
    axis_bc = await _raise_axis_from_parsed(ctx)
    await ctx.done()
    broadcasts: list[Broadcast] = [Broadcast("notice", notice=notice)]
    if axis_bc is not None:
        broadcasts.append(axis_bc)
    return broadcasts


async def _handle_clear(ctx: IngestContext) -> list[Broadcast]:
    """All-clear closes every open track — or, if clear_scope is set (a
    ballistic-only stand-down, "Відбій балістичної загрози з Криму"), only
    open tracks of that type, so an unrelated active shahed/jet track isn't
    incorrectly closed by a clear that never mentioned it."""
    session, parsed, when = ctx.session, ctx.parsed, ctx.when
    closed = await close_all_active(session, when, "all_clear", target_type=parsed.clear_scope)
    # A FULL all-clear ("Відбій тривоги") ends the attack — close its
    # incident too. A type-scoped clear ("Відбій балістики") ends an incident
    # only when it leaves NO open tracks: with the scoped type stood down and
    # nothing else flying, a still-"active" attack (banner + raion highlight)
    # reads as a bug; an open track of another type keeps it active.
    if parsed.clear_scope is None:
        ended = await end_active_incidents(session, when, "all_clear")
    else:
        ended = await end_incidents_without_open_tracks(session, when, "all_clear")
    # Surface the all-clear itself in the feed (a status-only broadcast is
    # invisible there) as a notice — the operator wants to SEE "відбій".
    notice = await _make_notice(session, "clear", parsed, ctx.source_id, when, ctx.message_id)
    await ctx.done()
    return (
        [Broadcast("status", t) for t in closed]
        + [Broadcast("attack", incident=inc) for inc in ended]
        + [Broadcast("notice", notice=notice)]
    )


async def _handle_lost_signal(ctx: IngestContext) -> list[Broadcast]:
    """"Дорозвідка" — ППО temporarily has no targets of the stated type (or,
    if unstated, none at all): a real stand-down signal, not a confirmed
    all-clear. Type-scoped when a type is named, else every open track. Each
    closed track gets its own event (inheriting that track's last known
    district) so the message is visible in the feed/track-inspect view
    instead of vanishing as a bare status broadcast."""
    session, parsed, when = ctx.session, ctx.parsed, ctx.when
    target = parsed.target_type if parsed.target_type != "unknown" else None
    closed = await close_all_active(session, when, "stand_down", target_type=target)
    pairs: list[tuple[Threat, ThreatEvent | None]] = []
    for t in closed:
        hit = _last_district_hit(t)
        ev = None
        if hit is not None:
            ev = _make_event(t.id, parsed, hit, ctx.source_id, ctx.message_id,
                             ctx.forwarded_from_id, when, ctx.decision_source,
                             ctx.reply_to_message_id, target_count=t.target_count,
                             forwarded_from_channel_id=ctx.forwarded_from_channel_id)
            session.add(ev)
        pairs.append((t, ev))
    if any(ev is not None for _, ev in pairs):
        await session.commit()
        for t, ev in pairs:
            if ev is not None:
                await apply_fusion(session, t)
    # A stand-down that leaves no open tracks ends the attack too — same
    # rationale as the type-scoped clear in _handle_clear above.
    ended = await end_incidents_without_open_tracks(session, when, "all_clear")
    await ctx.done()
    return [Broadcast("event" if ev is not None else "status", t, ev) for t, ev in pairs] + [
        Broadcast("attack", incident=inc) for inc in ended
    ]


async def _pulse_corroborates_axis(ctx: IngestContext) -> list[Broadcast] | None:
    """Fallback for a terse pulse when NO city-wide alert is open: if a
    directional axis is still open ("Загроза балістики з Брянська" → wedge),
    "Є вихід" is the spotter calling in the launch that axis warned about.
    Freshen the axis (keep the wedge alive) and surface the pulse as a
    directional notice inheriting the axis's origin/type, so it folds into that
    direction's feed card instead of being dropped as "не про загрозу". Returns
    None (still unhandled) when no axis matches — caller falls through."""
    session, parsed, when = ctx.session, ctx.parsed, ctx.when
    axis = await refresh_open_axis(session, when, parsed.target_type, raw_id=ctx.raw.id)
    if axis is None:
        return None
    notice = Notice(
        kind="directional", text=parsed.raw_text, target_type=axis.target_type,
        source_id=ctx.source_id, event_time=when, source_message_id=ctx.message_id,
        origin=axis.origin_key, generated_by="rule",
    )
    session.add(notice)
    await session.commit()
    await ctx.done()
    return [Broadcast("notice", notice=notice), Broadcast("axis", axis=axis)]


async def _handle_target_pulse(ctx: IngestContext) -> list[Broadcast] | None:
    """Terse target/launch pulse ("Ціль!", "Ще вихід", "3 ракети") — acted on
    while a city-wide alert is already open: a spotter calling the salvo in as
    it arrives. It corroborates that alert (an event on the sentinel district)
    and bumps the stated count. With no open city-wide alert it falls back to
    corroborating an open directional axis (_pulse_corroborates_axis); only if
    neither is open does it return None (too terse to localize on its own) and
    the caller falls through to the next check."""
    session, parsed, when = ctx.session, ctx.parsed, ctx.when
    city = await find_open_citywide(session, when)
    if city is None:
        stood = await find_stood_down_citywide(session, when)
        if stood is not None:
            city = reopen_track(stood)
    did = await citywide_district_id(session) if city is not None else None
    if city is None or did is None:
        return await _pulse_corroborates_axis(ctx)
    city.target_type = _upgrade_type(city.target_type, parsed.target_type)
    if parsed.target_count and parsed.target_count > city.target_count:
        city.target_count = parsed.target_count
    ev = ThreatEvent(
        threat_id=city.id, district_id=did, raw_text=parsed.raw_text,
        event_time=when, confidence=parsed.confidence, decision_source=ctx.decision_source,
        source_id=ctx.source_id, source_message_id=ctx.message_id,
        forwarded_from_id=ctx.forwarded_from_id,
        forwarded_from_channel_id=ctx.forwarded_from_channel_id,
        reply_to_message_id=ctx.reply_to_message_id,
        event_target_type=parsed.target_type, event_target_count=city.target_count,
    )
    session.add(ev)
    await session.commit()
    await apply_fusion(session, city)
    inc = await attach_to_incident(session, city, when, decoy=parsed.decoy,
                                   hypersonic=parsed.hypersonic)
    await ctx.done()
    return [Broadcast("event", city, ev), Broadcast("attack", incident=inc)]


async def _handle_summary(ctx: IngestContext) -> list[Broadcast]:
    """Retrospective attack summary ("Загалом ... 8 балістичних С-400") — info,
    not a live target: no map threat, but surfaced in the feed as a notice so
    the operator sees the tally of the attack."""
    notice = await _make_notice(ctx.session, "summary", ctx.parsed, ctx.source_id, ctx.when,
                                ctx.message_id)
    await ctx.done()
    return [Broadcast("notice", notice=notice)]


async def _handle_destroyed(ctx: IngestContext) -> list[Broadcast]:
    """Destroyed closes the matching open track. A "Мінус"-style reply names
    its target's chain directly; otherwise prefer the track over the named
    district, not merely the newest (see find_open_track)."""
    session, parsed, when = ctx.session, ctx.parsed, ctx.when
    track = await find_track_by_reply(session, ctx.source_id, ctx.reply_to_message_id)
    if track is None:
        prefer = {h.district_id for h in parsed.districts} or None
        # A destroyed message can land later than the normal grouping gap
        # (track_gap_minutes) but before the track would otherwise go
        # stale — look as far back as the stale window, not the grouping
        # window, so a reply-less "знищено" in that gap still finds its
        # track instead of silently matching nothing.
        track = await find_open_track(
            session, when, prefer_districts=prefer, gap_minutes=settings.track_stale_minutes
        )
    if track is None:
        await ctx.done()
        return []
    # A partial interception ("По ракетам мінус", "збито") must NOT close a
    # CITY-WIDE alert: scope='city' represents an ongoing city-level barrage
    # (10 S-400 over 20 min), not one trackable target. Closing it on the first
    # "мінус" split one barrage into two citywide tracks — the next "на місто"
    # callout couldn't rejoin the just-closed alert and spawned a second one
    # (live 2026-07-15: tracks 238+239). Only a real відбій (all_clear) or the
    # stale sweeper ends a city-wide alert; a мінус here is an informational
    # echo we drop rather than act on.
    if track.scope == "city":
        await ctx.done()
        return []
    # A closing message often names no district of its own ("Один збили,
    # залишився ще один") — inherit the track's last known position so the
    # message still becomes a real event (visible in the feed and in a
    # track's inspect view), instead of silently vanishing with only a
    # status-only broadcast the feed never displays.
    hit = parsed.districts[0] if parsed.districts else _last_district_hit(track)
    ev = None
    if hit is not None:
        ev = _make_event(track.id, parsed, hit, ctx.source_id,
                         ctx.message_id, ctx.forwarded_from_id, when, ctx.decision_source,
                         ctx.reply_to_message_id, target_count=track.target_count,
                         forwarded_from_channel_id=ctx.forwarded_from_channel_id)
        session.add(ev)
    close_track(track, when, "destroyed")
    await session.commit()
    await apply_fusion(session, track)
    await ctx.done()
    # "event" (not "status") whenever we actually created one, so the
    # frontend feed (which only appends 'event' broadcasts) shows it —
    # a status-only broadcast is silently invisible there.
    return [Broadcast("event" if ev is not None else "status", track, ev)]


async def _handle_impact(ctx: IngestContext) -> list[Broadcast]:
    """Impact / confirmed strike location ("влучання по будівлі в
    Дніпровському районі", "у Святошинському... пошкоджено будівлю"). This is
    a HIT, not an active inbound target — record it as its own terminal
    marker (closed immediately) so it persists on the map as a distinct
    impact pin and appears in the feed, without being mistaken for a target
    still in the air or absorbing later sightings over that district. Being
    closed, it's invisible to all track continuation/closure logic (which all
    filter closed_at IS NULL). Target type is whatever this message stated or
    inherited (often ballistic mid-attack)."""
    session, parsed, when = ctx.session, ctx.parsed, ctx.when
    # ONE impact marker PER DISTRICT — never merge districts into a single
    # threat. An impact is a POINT strike, not a trajectory: a ballistic can't
    # "move" Дарницький->Святошинський, yet a shared multi-district threat drew
    # exactly that bogus vector once later re-reports gave it several timestamps
    # (live 2026-07-15: T244 zigzagged two districts). Per district: a recent
    # impact over the SAME district is the SAME strike (two sources, one hit) ->
    # corroborate its marker; a different district gets its own marker.
    impacts: list[Broadcast] = []
    tracks_seen: list[Threat] = []
    for hit in parsed.districts:
        track = await find_recent_impact(session, hit.district_id, when)
        if track is None:
            track = Threat(
                target_type=parsed.target_type,
                status="impact",
                kind="impact",
                target_count=parsed.target_count or 1,
                closed_at=when,
            )
            session.add(track)
            await session.commit()
            log.info("track %s created (kind=impact, target_type=%s)", track.id, track.target_type)
        else:
            track.target_type = _upgrade_type(track.target_type, parsed.target_type)
        if track not in tracks_seen:
            tracks_seen.append(track)
        ev = _make_event(track.id, parsed, hit, ctx.source_id, ctx.message_id,
                         ctx.forwarded_from_id, when, ctx.decision_source, ctx.reply_to_message_id,
                         target_count=track.target_count,
                         forwarded_from_channel_id=ctx.forwarded_from_channel_id)
        session.add(ev)
        await session.commit()
        await apply_fusion(session, track)
        impacts.append(Broadcast("event", track, ev))
    # Every distinct impact marker joins the same attack (one barrage, many
    # hits); broadcast the incident once after the last attach.
    inc = None
    for track in tracks_seen:
        inc = await attach_to_incident(session, track, when, decoy=parsed.decoy,
                                       hypersonic=parsed.hypersonic)
    if inc is not None:
        impacts.append(Broadcast("attack", incident=inc))
    await ctx.done()
    return impacts


async def _handle_citywide(ctx: IngestContext) -> list[Broadcast]:
    """City-wide threat ("Ціль на місто!", "Балістика на Київ") — a strike
    aimed at the city as a whole that no spotter has localized to a raion
    (the sub-minute ballistic phase, when the map would otherwise be empty).
    Raise ONE city-level alert: continue an open one (repeated callouts
    corroborate it) or start a fresh one. Its event attaches to the sentinel
    district so it has a valid point; the frontend renders it as a banner,
    not a pin. Type upgrades like a normal track, so a bare "на місто" after
    "Балістика!" inherits ballistic (see type inheritance)."""
    session, parsed, when = ctx.session, ctx.parsed, ctx.when
    did = await citywide_district_id(session)
    if did is None:  # sentinel not seeded (shouldn't happen post-startup) — skip
        await ctx.done()
        return []
    track = await find_open_citywide(session, when)
    if track is None:
        stood = await find_stood_down_citywide(session, when)
        if stood is not None:
            track = reopen_track(stood)
    if track is None:
        track = Threat(target_type=parsed.target_type, status=_threat_status_for(parsed),
                       target_count=parsed.target_count or 1, scope="city")
        session.add(track)
        await session.commit()
        log.info("track %s created (scope=city, target_type=%s)", track.id, track.target_type)
    else:
        track.target_type = _upgrade_type(track.target_type, parsed.target_type)
        if parsed.status != "unconfirmed":
            promote_track(track)
        if parsed.target_count and parsed.target_count > track.target_count:
            track.target_count = parsed.target_count
    ev = ThreatEvent(
        threat_id=track.id, district_id=did, raw_text=parsed.raw_text,
        event_time=when, confidence=parsed.confidence, decision_source=ctx.decision_source,
        source_id=ctx.source_id, source_message_id=ctx.message_id,
        forwarded_from_id=ctx.forwarded_from_id,
        forwarded_from_channel_id=ctx.forwarded_from_channel_id,
        reply_to_message_id=ctx.reply_to_message_id,
        event_target_type=parsed.target_type, event_target_count=track.target_count,
        llm_summary=ctx.llm_summary,
    )
    session.add(ev)
    await session.commit()
    await apply_fusion(session, track)
    inc = await attach_to_incident(session, track, when, decoy=parsed.decoy,
                                   hypersonic=parsed.hypersonic)
    axis_bc = await _raise_axis_from_parsed(ctx)
    await ctx.done()
    out = [Broadcast("event", track, ev), Broadcast("attack", incident=inc)]
    if axis_bc is not None:
        out.append(axis_bc)
    return out


async def _handle_sighting(ctx: IngestContext) -> list[Broadcast]:
    """Sighting / confirmed / unconfirmed -> continue or start a track.
    (1) reply to an OPEN chain = authoritative same-target signal (beats
    is_new_target); (2) else corroboration — continue only a track recently
    over the same district; (3) else a new track. A reply into a CLOSED chain
    falls through to (2)/(3), so it won't glue onto the newest track."""
    session, parsed, when = ctx.session, ctx.parsed, ctx.when
    # Enumeration split is BALLISTIC-only: a ballistic salvo's «Вишневе Жуляни»
    # is two simultaneous impacts-in-seconds (gluing them zigzagged the map on
    # 07-18 and let the glued track steal later single-district callouts). On a
    # drone night the same shape («Троя,Оболонь») is usually ONE drone
    # meandering between adjacent raions — the track-eval ground truth
    # (drone/cruise nights) loses 16 points of session purity if those split,
    # and ballistic tracks never draw vectors anyway, so nothing is lost there.
    if (parsed.multi_targets and parsed.target_type == "ballistic"
            and not ctx.type_from_incident):
        return await _handle_multi_targets(ctx)
    track = await find_track_by_reply(session, ctx.source_id, ctx.reply_to_message_id)
    if track is None and not parsed.is_new_target:
        district_ids = {h.district_id for h in parsed.districts}
        track = await find_corroborating_track(session, when, district_ids, as_of=ctx.as_of)
        if track is None:
            stood = await find_stood_down_track(session, when, district_ids)
            if stood is not None:
                track = reopen_track(stood)
    if track is None:
        track = Threat(target_type=parsed.target_type, status=_threat_status_for(parsed),
                       target_count=parsed.target_count or 1)
        session.add(track)
        await session.commit()
        log.info("track %s created (target_type=%s)", track.id, track.target_type)
    else:
        track.target_type = _upgrade_type(track.target_type, parsed.target_type)
        if parsed.status != "unconfirmed":
            promote_track(track)
        # Group size only grows within a chain (2х -> "їх вже 3х").
        if parsed.target_count and parsed.target_count > track.target_count:
            track.target_count = parsed.target_count

    broadcasts: list[Broadcast] = []
    # One event per mentioned district, in movement order.
    for hit in parsed.districts:
        ev = _make_event(track.id, parsed, hit, ctx.source_id, ctx.message_id,
                         ctx.forwarded_from_id, when, ctx.decision_source, ctx.reply_to_message_id,
                         target_count=track.target_count,
                         forwarded_from_channel_id=ctx.forwarded_from_channel_id,
                         llm_summary=ctx.llm_summary)
        session.add(ev)
        await session.commit()
        await apply_fusion(session, track)
        broadcasts.append(Broadcast("event", track, ev))

    inc = await attach_to_incident(session, track, when, decoy=parsed.decoy,
                                   hypersonic=parsed.hypersonic)
    broadcasts.append(Broadcast("attack", incident=inc))
    axis_bc = await _raise_axis_from_parsed(ctx)
    if axis_bc is not None:
        broadcasts.append(axis_bc)
    await ctx.done()
    return broadcasts


async def _handle_multi_targets(ctx: IngestContext) -> list[Broadcast]:
    """A bare enumeration of districts ("Вишневе Жуляни", "Особливо Поділ,
    Святошин та Жуляни!") names SIMULTANEOUS separate targets — each district
    continues/starts its OWN track. Gluing them all onto one track (the old
    behavior) recreated the zigzag mega-track on 07-18 AND poisoned
    corroboration: the glued track's "latest district" kept stealing the next
    single-district callouts from their real tracks. Reply-joining is skipped
    on purpose — one reply chain can't own several simultaneous targets."""
    session, parsed, when = ctx.session, ctx.parsed, ctx.when
    broadcasts: list[Broadcast] = []
    inc = None
    for hit in parsed.districts:
        track = None
        if not parsed.is_new_target:
            track = await find_corroborating_track(session, when, {hit.district_id},
                                                   as_of=ctx.as_of)
            if track is None:
                stood = await find_stood_down_track(session, when, {hit.district_id})
                if stood is not None:
                    track = reopen_track(stood)
        if track is None:
            track = Threat(target_type=parsed.target_type, status=_threat_status_for(parsed),
                           target_count=parsed.target_count or 1)
            session.add(track)
            await session.commit()
            log.info("track %s created (target_type=%s, multi-target enumeration)",
                     track.id, track.target_type)
        else:
            track.target_type = _upgrade_type(track.target_type, parsed.target_type)
            if parsed.status != "unconfirmed":
                promote_track(track)
        ev = _make_event(track.id, parsed, hit, ctx.source_id, ctx.message_id,
                         ctx.forwarded_from_id, when, ctx.decision_source,
                         ctx.reply_to_message_id, target_count=track.target_count,
                         forwarded_from_channel_id=ctx.forwarded_from_channel_id,
                         llm_summary=ctx.llm_summary)
        session.add(ev)
        await session.commit()
        await apply_fusion(session, track)
        broadcasts.append(Broadcast("event", track, ev))
        inc = await attach_to_incident(session, track, when, decoy=parsed.decoy,
                                       hypersonic=parsed.hypersonic)
    if inc is not None:
        broadcasts.append(Broadcast("attack", incident=inc))
    axis_bc = await _raise_axis_from_parsed(ctx)
    if axis_bc is not None:
        broadcasts.append(axis_bc)
    await ctx.done()
    return broadcasts


def _ingest_outcome(broadcasts: list[Broadcast]) -> str:
    """Domain result of one pipeline pass, for the Logfire span — the thing
    auto-instrumentation can't see. `threat` = a real map target/impact was
    created or corroborated (an event fired); `notice` = only informational
    surfaces (directional/summary/clear/status-only/axis); `dropped` = nothing
    actionable, raw row kept but no broadcast."""
    if any(b.type == "event" for b in broadcasts):
        return "threat"
    if broadcasts:
        return "notice"
    return "dropped"


async def process_parsed(
    session,
    *,
    raw: RawMessage,
    text: str,
    matcher: DistrictMatcher,
    when: datetime,
    source_id: int | None,
    message_id: int | None,
    forwarded_from_id: int | None,
    forwarded_from_channel_id: int | None = None,
    reply_to_message_id: int | None,
    triage: str = "live",
) -> list[Broadcast]:
    """Parse -> track -> fuse an ALREADY-PERSISTED raw message.

    Split out from `_ingest_locked` so `scripts/reprocess_raw.py` can replay
    existing `raw_messages` rows through the current parser/gazetteer/tracking
    logic (e.g. after growing the gazetteer) without re-inserting them — the
    ingest-level dedup guard would otherwise make that a no-op.

    `triage` mode:
      * 'live'   — enqueue a qualifying message for the async triage engine.
      * 'replay' — route the STORED llm_response verdict inline (no API call, no
        queue), so a reprocess deterministically reproduces what triage did, at
        each message's natural chronological position (see reprocess.py).
      * 'off'    — no triage at all.
    """
    # One custom span per pass, parent to the auto-instrumented SQL/LLM child
    # spans. It carries the domain facts auto-instrumentation can't see —
    # decision_source, target_type, and the final outcome — so Logfire can answer
    # "how many messages/hour landed in dropped" or "what share of decisions came
    # from the LLM" by attribute filter, not log-text parsing. Dormant (no-op)
    # until observability is set up, so reprocess/eval/tests are unaffected.
    with ingest_span("ingest_message") as span:
        parsed, decision_source, llm_attempted, llm_usage, llm_response = await _resolve(text, matcher)
        raw.llm_attempted = llm_attempted
        if llm_usage is not None:
            raw.llm_input_tokens = llm_usage.input_tokens
            raw.llm_output_tokens = llm_usage.output_tokens
            raw.llm_cost_usd = llm_usage.cost_usd
        if llm_response is not None:
            raw.llm_response = llm_response

        # Cross-message type inheritance: record this message's stated type, or
        # inherit a recent one from the same channel onto a bare-toponym sighting
        # ("Троя" mid-ballistic-attack -> missile, not unknown). Runs before every
        # branch below so a typed post updates the context even when it produces no
        # event of its own (e.g. a district-less "Балістика!").
        _note_and_inherit_type(parsed, source_id, when)

        # Second-tier fallback: a still-untyped sighting during a live attack
        # takes the open incident's dominant type. The per-channel window above
        # is only 5 min and channel-scoped — during the 07-18 toponym barrage
        # («Нивки», «Обухів»…) it kept expiring while the OTHER channel was
        # shouting «балістика», leaving 12 tracks typed "unknown" mid-salvo.
        # A later explicitly-typed event that disagrees still surfaces as a
        # fusion conflict, same as any cross-family mismatch.
        type_from_incident = False
        if parsed.target_type == "unknown" and (parsed.districts or parsed.citywide):
            inc = await find_active_incident(session, when)
            if inc is not None and inc.target_type != "unknown":
                parsed.target_type = inc.target_type
                type_from_incident = True

        span.set_attribute("decision_source", decision_source)
        span.set_attribute("target_type", parsed.target_type)
        span.set_attribute("llm_attempted", llm_attempted)

        ctx = IngestContext(
            session=session, raw=raw, parsed=parsed, decision_source=decision_source,
            when=when, source_id=source_id, message_id=message_id,
            forwarded_from_id=forwarded_from_id,
            forwarded_from_channel_id=forwarded_from_channel_id,
            reply_to_message_id=reply_to_message_id,
            llm_summary=(llm_response.get("summary") or None
                         if llm_response is not None and decision_source == "llm" else None),
            type_from_incident=type_from_incident,
        )

        # Async triage: hand a district-less/suppressed-but-threat-flavored message
        # to the second-pass engine (which surfaces directional/forecast/status
        # notices, feeds the axis layer, and — behind a flag — rescues a wrongly
        # suppressed live threat). Reuses the inline verdict if one exists (no second
        # API call). Marked on the raw row so /raw shows where it went.
        triage_extra: list[Broadcast] = []
        if triage == "live":
            from .triage import TriageJob, enqueue_job, should_triage

            if should_triage(parsed, decision_source, llm_response):
                job = TriageJob(
                    raw_id=raw.id, text=text, when=when, source_id=source_id,
                    message_id=message_id, reply_to_message_id=reply_to_message_id,
                    forwarded_from_id=forwarded_from_id,
                    forwarded_from_channel_id=forwarded_from_channel_id,
                    verdict=llm_response,
                )
                raw.triage_state = "pending" if enqueue_job(job) else "skipped"
        elif triage == "replay" and raw.llm_response is not None:
            # Deterministic reprocess: route the STORED verdict inline (no API, no
            # queue), at this message's natural chronological position.
            triage_extra = await _replay_triage_verdict(ctx, raw.llm_response, matcher)

        result = await _dispatch(ctx)
        broadcasts = result + triage_extra
        outcome = _ingest_outcome(broadcasts)
        span.set_attribute("outcome", outcome)

        # Domain metrics (survive head-sampling; feed rate/hit-rate dashboards).
        metrics.record_ingest(outcome, decision_source)
        # An LLM call that was attempted resolved to a hit iff it recovered a
        # district — which is exactly what decision_source=='llm' means here
        # (see _resolve). llm_attempted with decision_source=='rule' is a miss.
        if llm_attempted:
            metrics.record_llm(hit=decision_source == "llm")
        return broadcasts


async def _dispatch(ctx: IngestContext) -> list[Broadcast]:
    """Route a parsed spotter message to its handler, in fixed precedence order."""
    parsed = ctx.parsed
    # 2a. All-clear. An authoritative FULL "Відбій тривоги" (clear_scope=None,
    #     closes EVERY track) comes ONLY from the official alert channel
    #     (process_parsed_alert closes all tracks on its city end) — a spotter's
    #     full відбій is informal/premature/noisy (the N85 case, plus the whole
    #     "чекаємо/будемо очікувати відбій" class) and must not close every live
    #     track, so it is inert here. A TYPE-SCOPED spotter stand-down ("Відбій
    #     балістичної загрози" -> ballistic only) is KEPT: a narrow tactical
    #     signal the city/oblast-level official alert structurally can't express.
    if parsed.status == "clear":
        if parsed.clear_scope is None:
            await ctx.done()
            return []
        return await _handle_clear(ctx)

    # 2a-bis. "Дорозвідка" stand-down. A MIXED message («Дорозвідка триває, але
    #     паралельно триває загроза балістики з Брянщини…») carries a live
    #     directional threat next to the stand-down — the live half wins (raise
    #     the axis, don't close everything on it): on 07-18 such a message was
    #     swallowed as a plain stand-down while warning of 3 launch directions.
    if parsed.lost_signal:
        if parsed.directional:
            return await _handle_directional(ctx)
        return await _handle_lost_signal(ctx)

    # 2a-ter. Terse target/launch pulse — falls through to the checks below
    #     when there's no open city-wide alert to corroborate.
    if parsed.target_pulse:
        result = await _handle_target_pulse(ctx)
        if result is not None:
            return result

    # 2a-quater. Retrospective attack summary.
    if parsed.summary:
        return await _handle_summary(ctx)

    # 2a-quinquies. Directional/origin callout with no raion -> a map axis.
    if parsed.directional:
        return await _handle_directional(ctx)

    # 2b. Nothing localizable/actionable — keep the raw row, emit nothing.
    if not parsed.matched:
        await ctx.done()
        return []

    # 2c. Destroyed.
    if parsed.status == "destroyed":
        return await _handle_destroyed(ctx)

    # 2c-bis. Impact / confirmed strike location.
    if parsed.impact:
        return await _handle_impact(ctx)

    # 2c-ter. City-wide threat.
    if parsed.citywide:
        return await _handle_citywide(ctx)

    # 2d. Sighting / confirmed / unconfirmed -> continue or start a track.
    return await _handle_sighting(ctx)


async def process_rescued(session, *, raw: RawMessage, job, verdict: dict,
                          matcher: DistrictMatcher | None = None) -> list[Broadcast]:
    """Re-inject a triage-rescued verdict through the normal sighting/citywide
    handlers, at the message's ORIGINAL timestamp and with decision_source=
    'triage'. Reusing the live handlers means tracking/fusion/incident-attach/
    broadcast all behave identically to a live message. Deliberately does NOT
    call _note_and_inherit_type (a late rescue must not inject a stale type into
    the live per-channel context) and evaluates corroboration as-of the original
    time (ctx.as_of)."""
    if matcher is None:
        from ..models import District
        districts = list(await session.scalars(select(District)))
        matcher = DistrictMatcher(districts)
    name_by_id = dict(matcher.districts_index)
    hits = [DistrictHit(did, name_by_id[did], i)
            for i, did in enumerate(verdict.get("district_ids", [])) if did in name_by_id]
    status = verdict.get("status", "sighting")
    if status not in ("confirmed", "unconfirmed", "sighting"):
        status = "sighting"
    citywide = verdict.get("category") == "citywide" and not hits
    parsed = ParseResult(
        target_type=verdict.get("target_type", "unknown"),
        status=status,
        is_new_target=bool(verdict.get("is_new_target", False)),
        districts=hits,
        confidence=float(verdict.get("confidence", 0.5)),
        raw_text=job.text,
        matched=bool(hits) or citywide,
        citywide=citywide,
    )
    ctx = IngestContext(
        session=session, raw=raw, parsed=parsed, decision_source="triage",
        when=job.when, source_id=job.source_id, message_id=job.message_id,
        forwarded_from_id=job.forwarded_from_id,
        forwarded_from_channel_id=job.forwarded_from_channel_id,
        reply_to_message_id=job.reply_to_message_id,
        as_of=job.when,
        llm_summary=(verdict.get("summary") or None),
    )
    if citywide:
        return await _handle_citywide(ctx)
    if not hits:
        await ctx.done()
        return []
    return await _handle_sighting(ctx)


async def _replay_triage_verdict(ctx: IngestContext, verdict: dict,
                                 matcher: DistrictMatcher) -> list[Broadcast]:
    """Deterministic reprocess: route a STORED verdict through the same routing
    table the live async engine uses (triage.route_verdict), but inline — no
    queue, no API, no age gate (each verdict is re-applied at its own position)."""
    from .triage import TriageJob, route_verdict

    job = TriageJob(
        raw_id=ctx.raw.id, text=ctx.parsed.raw_text, when=ctx.when, source_id=ctx.source_id,
        message_id=ctx.message_id, reply_to_message_id=ctx.reply_to_message_id,
        forwarded_from_id=ctx.forwarded_from_id,
        forwarded_from_channel_id=ctx.forwarded_from_channel_id, verdict=verdict,
    )
    broadcasts, action, _state = await route_verdict(
        ctx.session, ctx.raw, job, verdict, enforce_age=False
    )
    ctx.raw.triage_action = action
    ctx.raw.triage_state = "done"
    return broadcasts


async def ingest_alert_message(
    session,
    *,
    text: str,
    when: datetime,
    source_id: int | None = None,
    message_id: int | None = None,
) -> list[Broadcast]:
    """Serialized entry point for the OFFICIAL alert channel — separate from
    `ingest_message` because it needs none of the spotter context (district
    matcher, reply-threading, forward attribution: this channel never
    reply-threads or reposts). Shares `_ingest_lock` with the spotter path so
    the two can never race on the same raw-message dedup guard."""
    async with _ingest_lock:
        return await _alert_ingest_locked(session, text=text, when=when,
                                          source_id=source_id, message_id=message_id)


async def _alert_ingest_locked(
    session, *, text: str, when: datetime, source_id: int | None, message_id: int | None
) -> list[Broadcast]:
    # Deliberately NOT "raw storage first" here, unlike the spotter pipeline
    # (see ingest_message's docstring) — this channel's non-alert traffic is
    # bulk city news (infra updates, recaps), not spotter data worth growing
    # an eval set from, so a message that doesn't parse as a start/end is
    # dropped without ever touching raw_messages.
    if parse_alert_message(text) is None:
        return []

    if message_id is not None:
        dup = await session.scalar(
            select(RawMessage.id).where(
                RawMessage.source_id == source_id, RawMessage.message_id == message_id
            )
        )
        if dup is not None:
            return []

    raw = RawMessage(source_id=source_id, message_id=message_id, text=text, event_time=when)
    session.add(raw)
    await session.commit()

    return await process_parsed_alert(session, raw=raw, text=text, when=when, source_id=source_id)


async def process_parsed_alert(
    session, *, raw: RawMessage, text: str, when: datetime, source_id: int | None
) -> list[Broadcast]:
    """Parse -> apply an ALREADY-PERSISTED alert-channel raw message. Split
    out from `_alert_ingest_locked` so `reprocess.py` can replay stored
    alert-channel messages the same way it replays spotter ones. The
    `parsed is None` branch is now unreachable from live ingestion (see
    `_alert_ingest_locked`, which drops non-alert text before it's ever
    persisted) but stays live for `reprocess.py` replaying raw_messages rows
    stored before that filter existed."""
    parsed = parse_alert_message(text)
    raw.processed = True
    if parsed is None:
        await session.commit()
        return []

    signal = AlertSignal(
        scope=parsed.scope, action=parsed.action, when=when,
        provider="telegram", raw_id=raw.id,
    )
    alert = await apply_alert_signal(session, signal)
    await session.commit()
    if alert is None:  # idempotent no-op (already open / nothing to end)
        return []
    broadcasts: list[Broadcast] = [Broadcast("alert", alert=alert)]

    # A CITY alert ending is the end of the whole attack: close every open
    # track (reason='all_clear', same as a spotter відбій) and end every
    # active incident (ended_reason='alert_end'). This is naturally
    # idempotent alongside the spotter відбій path above — whichever lands
    # first does the real work; `alert is None` already returned early for a
    # repeat, and close_all_active/end_active_incidents are no-ops when
    # nothing is open — so an official + spotter відбій seconds apart dedupe
    # instead of double-firing.
    if parsed.action == "end" and parsed.scope == "city":
        closed_tracks = await close_all_active(session, when, "all_clear")
        broadcasts += [Broadcast("status", t) for t in closed_tracks]
        ended_incidents = await end_active_incidents(session, when, "alert_end")
        broadcasts += [Broadcast("attack", incident=inc) for inc in ended_incidents]
        # Surface the all-clear in the feed too (the banner alone is invisible
        # in the Стрічка подій). This "Відбій" card used to be raised by the
        # spotter відбій path, which no longer fires a full clear — the feed
        # card now comes from the authoritative official channel instead.
        notice = Notice(kind="clear", text=text, target_type="unknown",
                        source_id=source_id, event_time=when,
                        source_message_id=raw.message_id)
        session.add(notice)
        await session.commit()
        broadcasts.append(Broadcast("notice", notice=notice))

    return broadcasts


async def _make_notice(session, kind: str, parsed: ParseResult, source_id: int | None,
                        when: datetime, message_id: int | None = None) -> Notice:
    notice = Notice(kind=kind, text=parsed.raw_text, target_type=parsed.target_type,
                    source_id=source_id, event_time=when, source_message_id=message_id)
    session.add(notice)
    await session.commit()
    return notice


def _last_district_hit(track: Threat) -> DistrictHit | None:
    """Synthesize a hit for the track's most recently reported district, for a
    closing message that names no district of its own."""
    if not track.events:
        return None
    last = max(track.events, key=lambda e: e.event_time)
    return DistrictHit(district_id=last.district_id, name="", position=0)


def _make_event(threat_id, parsed: ParseResult, hit, source_id, message_id,
                forwarded_from_id, when: datetime, decision_source: str,
                reply_to_message_id: int | None = None,
                target_count: int = 1,
                forwarded_from_channel_id: int | None = None,
                llm_summary: str | None = None) -> ThreatEvent:
    return ThreatEvent(
        threat_id=threat_id,
        district_id=hit.district_id,
        raw_text=parsed.raw_text,
        event_time=when,
        confidence=parsed.confidence,
        decision_source=decision_source,
        source_id=source_id,
        source_message_id=message_id,
        forwarded_from_id=forwarded_from_id,
        forwarded_from_channel_id=forwarded_from_channel_id,
        reply_to_message_id=reply_to_message_id,
        event_target_type=parsed.target_type,
        event_target_count=target_count,
        llm_summary=llm_summary,
    )

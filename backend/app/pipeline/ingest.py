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
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select

from ..domain.alerts import AlertSignal, apply_alert_signal
from ..domain.districts import citywide_district_id
from ..domain.incidents import attach_to_incident, end_active_incidents
from ..domain.lifecycle import close_track, promote_track
from ..domain.tracking import (
    apply_fusion,
    close_all_active,
    find_corroborating_track,
    find_open_citywide,
    find_open_track,
    find_recent_impact,
    find_track_by_reply,
)
from ..config import settings
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


# Other oblasts/cities/border regions this feed regularly mentions. When one is
# the target's LOCATION ("ціль на Дніпро", "загроза у Сумах") the threat is
# someone else's and an LLM call can't recover a Kyiv district — same set the
# LLM's own system prompt (parsing.llm._SYSTEM) is told to return empty for.
# But when one is only the ORIGIN of an INBOUND target ("БпЛА з Чернігівщини",
# "реактивні від Сум" — heading toward Kyiv), the message IS Kyiv-relevant:
# suppressing it here (the old blanket behavior) dropped exactly the "до нас з
# півночі" callouts before the triage LLM ever saw them. So origin mentions no
# longer suppress; only a target-location mention does (see _target_elsewhere).
_OTHER_OBLAST = ("чернігівщин", "чернігів", "брянщин", "курщин", "ростов", "воронеж",
                  "дніпропетровщин", "дніпро", "запоріжж", "миколаївщин", "сумщин",
                  "полтавщин", "харківщин", "харков", "білорус", "крим",
                  "житомирщин", "вінницьк", "черкащин", "одещин", "херсонщин")

_OBLAST_ALT = "|".join(sorted(map(re.escape, _OTHER_OBLAST), key=len, reverse=True))
# Any other-oblast mention.
_OBLAST_ANY_RE = re.compile(r"(?<![а-яіїєґ])(?:" + _OBLAST_ALT + r")")
# An other-oblast in ORIGIN position: a "from" preposition (з/зі/із/від), with an
# optional "боку/напрямку/району/межах/р-ну" bridge ("з боку Сумщини", "з району
# Ростова"), immediately before the oblast token. Everything else — "на Дніпро",
# "у Сумах", a bare "Чернігівщина під ударом" — counts as a target location.
_OBLAST_ORIGIN_RE = re.compile(
    r"(?<![а-яіїєґ])(?:з|зі|із|від)\s+"
    r"(?:боку\s+|напрямку\s+|району\s+|р-ну\s+|межах\s+|межа\w*\s+)?"
    r"(?:" + _OBLAST_ALT + r")"
)


def _target_elsewhere(norm: str) -> bool:
    """True if the message names another oblast as a target LOCATION (not merely
    an inbound target's origin) — then rules found no Kyiv district because the
    threat genuinely isn't ours, and the LLM can't recover one either. An
    origin-only mention ("з Чернігівщини", heading to us) returns False so the
    inbound callout still reaches the triage LLM. Conservative when unclear: a
    non-origin oblast mention suppresses, matching the prior blanket behavior."""
    total = len(_OBLAST_ANY_RE.findall(norm))
    if total == 0:
        return False
    origins = len(_OBLAST_ORIGIN_RE.findall(norm))
    return origins < total


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
    if parsed.political_quote:  # official statement repost — not a live target
        return False
    if parsed.lost_signal:  # "дорозвідка" stand-down — handled directly by ingest, not a live target
        return False
    if parsed.citywide:  # city-level alert with no raion — LLM can't localize it further
        return False
    if parsed.summary:  # retrospective recap, not a live target — nothing to localize
        return False
    if parsed.target_pulse:  # terse pulse, no place — nothing for the LLM to localize
        return False
    if parsed.districts or parsed.status in ("clear", "destroyed"):
        return False
    if _target_elsewhere(normalize(parsed.raw_text)):
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

    async def done(self) -> None:
        self.raw.processed = True
        await self.session.commit()


async def _handle_clear(ctx: IngestContext) -> list[Broadcast]:
    """All-clear closes every open track — or, if clear_scope is set (a
    ballistic-only stand-down, "Відбій балістичної загрози з Криму"), only
    open tracks of that type, so an unrelated active shahed/jet track isn't
    incorrectly closed by a clear that never mentioned it."""
    session, parsed, when = ctx.session, ctx.parsed, ctx.when
    closed = await close_all_active(session, when, "all_clear", target_type=parsed.clear_scope)
    # A FULL all-clear ("Відбій тривоги") ends the attack — close its
    # incident too. A type-scoped clear ("Відбій балістики") leaves the
    # incident open: other target types may still be inbound.
    if parsed.clear_scope is None:
        await end_active_incidents(session, when, "all_clear")
    # Surface the all-clear itself in the feed (a status-only broadcast is
    # invisible there) as a notice — the operator wants to SEE "відбій".
    notice = await _make_notice(session, "clear", parsed, ctx.source_id, when, ctx.message_id)
    await ctx.done()
    return [Broadcast("status", t) for t in closed] + [Broadcast("notice", notice=notice)]


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
    await ctx.done()
    return [Broadcast("event" if ev is not None else "status", t, ev) for t, ev in pairs]


async def _handle_target_pulse(ctx: IngestContext) -> list[Broadcast] | None:
    """Terse target/launch pulse ("Ціль!", "Ще вихід", "3 ракети") — acted on
    ONLY while a city-wide alert is already open: a spotter calling the salvo
    in as it arrives. It corroborates that alert (an event on the sentinel
    district) and bumps the stated count. Returns None (not handled) when
    there's no open city-wide alert to corroborate — the caller falls through
    to the next check (too terse to localize on its own)."""
    session, parsed, when = ctx.session, ctx.parsed, ctx.when
    city = await find_open_citywide(session, when)
    did = await citywide_district_id(session) if city is not None else None
    if city is None or did is None:
        return None
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
    # Dedup: a recent impact over the SAME district is the SAME strike (two
    # sources, one hit) — corroborate that marker instead of stacking a
    # second pin on the identical point. Else a fresh impact marker.
    track = await find_recent_impact(session, parsed.districts[0].district_id, when)
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
    impacts: list[Broadcast] = []
    for hit in parsed.districts:
        ev = _make_event(track.id, parsed, hit, ctx.source_id, ctx.message_id,
                         ctx.forwarded_from_id, when, ctx.decision_source, ctx.reply_to_message_id,
                         target_count=track.target_count,
                         forwarded_from_channel_id=ctx.forwarded_from_channel_id)
        session.add(ev)
        await session.commit()
        await apply_fusion(session, track)
        impacts.append(Broadcast("event", track, ev))
    inc = await attach_to_incident(session, track, when, decoy=parsed.decoy,
                                   hypersonic=parsed.hypersonic)
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
    )
    session.add(ev)
    await session.commit()
    await apply_fusion(session, track)
    inc = await attach_to_incident(session, track, when, decoy=parsed.decoy,
                                   hypersonic=parsed.hypersonic)
    await ctx.done()
    return [Broadcast("event", track, ev), Broadcast("attack", incident=inc)]


async def _handle_sighting(ctx: IngestContext) -> list[Broadcast]:
    """Sighting / confirmed / unconfirmed -> continue or start a track.
    (1) reply to an OPEN chain = authoritative same-target signal (beats
    is_new_target); (2) else corroboration — continue only a track recently
    over the same district; (3) else a new track. A reply into a CLOSED chain
    falls through to (2)/(3), so it won't glue onto the newest track."""
    session, parsed, when = ctx.session, ctx.parsed, ctx.when
    track = await find_track_by_reply(session, ctx.source_id, ctx.reply_to_message_id)
    if track is None and not parsed.is_new_target:
        district_ids = {h.district_id for h in parsed.districts}
        track = await find_corroborating_track(session, when, district_ids)
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
                         forwarded_from_channel_id=ctx.forwarded_from_channel_id)
        session.add(ev)
        await session.commit()
        await apply_fusion(session, track)
        broadcasts.append(Broadcast("event", track, ev))

    inc = await attach_to_incident(session, track, when, decoy=parsed.decoy,
                                   hypersonic=parsed.hypersonic)
    broadcasts.append(Broadcast("attack", incident=inc))
    await ctx.done()
    return broadcasts


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
) -> list[Broadcast]:
    """Parse -> track -> fuse an ALREADY-PERSISTED raw message.

    Split out from `_ingest_locked` so `scripts/reprocess_raw.py` can replay
    existing `raw_messages` rows through the current parser/gazetteer/tracking
    logic (e.g. after growing the gazetteer) without re-inserting them — the
    ingest-level dedup guard would otherwise make that a no-op.
    """
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

    ctx = IngestContext(
        session=session, raw=raw, parsed=parsed, decision_source=decision_source,
        when=when, source_id=source_id, message_id=message_id,
        forwarded_from_id=forwarded_from_id,
        forwarded_from_channel_id=forwarded_from_channel_id,
        reply_to_message_id=reply_to_message_id,
    )

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

    # 2a-bis. "Дорозвідка" stand-down.
    if parsed.lost_signal:
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
                forwarded_from_channel_id: int | None = None) -> ThreatEvent:
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
    )

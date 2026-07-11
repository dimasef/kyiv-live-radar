"""Ingest pipeline: one raw message -> stored + parsed + tracked + broadcast.

Single entry point (`ingest_message`) shared by the Telethon listener and the
text simulator, so both exercise the exact same real parsing/tracking code.
`_process_parsed` is the reusable inner half (parse -> track -> fuse) for an
already-stored raw message — also used by `scripts/reprocess_raw.py` to replay
history through an improved parser/gazetteer.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select

from .config import settings
from .gazetteer import CITYWIDE_NAME_EN
from .incidents import attach_to_incident, end_active_incidents
from .parser import DistrictHit, DistrictMatcher, ParseResult, normalize, parse_message
from .models import District, Notice, RawMessage, Threat, ThreatEvent
from .tracking import (
    apply_fusion,
    close_all_active,
    find_corroborating_track,
    find_open_citywide,
    find_open_track,
    find_recent_impact,
    find_track_by_reply,
)

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
# call, since _should_fallback short-circuits to False whenever districts exist.
_recent_type: dict[int, tuple[str, datetime]] = {}


# Cached DB id of the city-wide sentinel district (see gazetteer.CITYWIDE_NAME_EN).
# Resolved once — the row is seeded at startup and never changes.
_citywide_district_id: int | None = None


async def _citywide_did(session) -> int | None:
    global _citywide_district_id
    if _citywide_district_id is None:
        _citywide_district_id = await session.scalar(
            select(District.id).where(District.name_en == CITYWIDE_NAME_EN)
        )
    return _citywide_district_id


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


@dataclass
class Broadcast:
    type: str  # 'event' | 'status' | 'notice'
    threat: Threat | None = None
    event: ThreatEvent | None = None
    notice: "Notice | None" = None


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


# Other oblasts/cities/border regions this feed regularly mentions as a launch
# origin or transit point ("з Брянщини", "на Чернігівщині") — the exact same
# set the LLM's own system prompt (llm_fallback._SYSTEM) is told to return
# empty for. If rules found no Kyiv-area district AND the message only names
# one of these, an LLM call can't recover anything either — it's paying for a
# guaranteed-empty response. Only checked once districts is already empty, so
# this never masks a real Kyiv-area place mentioned alongside one of these.
_OTHER_OBLAST = ("чернігівщин", "чернігів", "брянщин", "курщин", "ростов", "воронеж",
                  "дніпропетровщин", "дніпро", "запоріжж", "миколаївщин", "сумщин",
                  "полтавщин", "харківщин", "харков", "білорус", "крим",
                  "житомирщин", "вінницьк", "черкащин", "одещин", "херсонщин")


def _should_fallback(parsed: ParseResult) -> bool:
    """Route to the LLM only when rules couldn't localize a threat-flavored
    message — not for junk/news and not when rules already succeeded."""
    if parsed.aftermath:  # consequence/casualty news — not a live target
        return False
    if parsed.siren_only:  # technical "alarm is on here" echo — not a live target
        return False
    if parsed.negated:  # explicit denial ("не йде на...") — not a live target
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
    if any(w in normalize(parsed.raw_text) for w in _OTHER_OBLAST):
        return False
    return parsed.target_type != "unknown" or parsed.status in ("confirmed", "unconfirmed")


async def _resolve(text: str, matcher: DistrictMatcher) -> tuple[ParseResult, str]:
    """Rule-based first; LLM fallback only when warranted and configured."""
    parsed = parse_message(text, matcher)
    if settings.llm_fallback_enabled and settings.anthropic_api_key and _should_fallback(parsed):
        from .llm_fallback import llm_extract

        llm = await llm_extract(text, matcher)
        # Trust the LLM for LOCALIZATION only — use its result only when it
        # actually recovered a district. Never let it declare an all-clear /
        # destroyed on its own: rules own those via explicit keywords
        # ("відбій"/"збито"), and a keyword-detected stand-down never reaches the
        # LLM anyway (see _should_fallback). Letting the LLM infer a clear from a
        # reassuring tone ("масованих пусків немає… відпочивайте") produced false
        # "Відбій" feed entries AND risked closing active tracks via close_all_active.
        if llm is not None and llm.districts:
            return llm, "llm"
    return parsed, "rule"


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
        reply_to_message_id=reply_to_message_id,
    )
    session.add(raw)
    await session.commit()

    return await _process_parsed(
        session,
        raw=raw,
        text=text,
        matcher=matcher,
        when=when,
        source_id=source_id,
        message_id=message_id,
        forwarded_from_id=forwarded_from_id,
        reply_to_message_id=reply_to_message_id,
    )


async def _process_parsed(
    session,
    *,
    raw: RawMessage,
    text: str,
    matcher: DistrictMatcher,
    when: datetime,
    source_id: int | None,
    message_id: int | None,
    forwarded_from_id: int | None,
    reply_to_message_id: int | None,
) -> list[Broadcast]:
    """Parse -> track -> fuse an ALREADY-PERSISTED raw message.

    Split out from `_ingest_locked` so `scripts/reprocess_raw.py` can replay
    existing `raw_messages` rows through the current parser/gazetteer/tracking
    logic (e.g. after growing the gazetteer) without re-inserting them — the
    ingest-level dedup guard would otherwise make that a no-op.
    """
    parsed, decision_source = await _resolve(text, matcher)

    # Cross-message type inheritance: record this message's stated type, or
    # inherit a recent one from the same channel onto a bare-toponym sighting
    # ("Троя" mid-ballistic-attack -> missile, not unknown). Runs before every
    # branch below so a typed post updates the context even when it produces no
    # event of its own (e.g. a district-less "Балістика!").
    _note_and_inherit_type(parsed, source_id, when)

    async def done() -> None:
        raw.processed = True
        await session.commit()

    # 2a. All-clear closes every open track — or, if clear_scope is set (a
    # ballistic-only stand-down, "Відбій балістичної загрози з Криму"), only
    # open tracks of that type, so an unrelated active shahed/jet track isn't
    # incorrectly closed by a clear that never mentioned it.
    if parsed.status == "clear":
        closed = await close_all_active(session, when, target_type=parsed.clear_scope)
        # A FULL all-clear ("Відбій тривоги") ends the attack — close its
        # incident too. A type-scoped clear ("Відбій балістики") leaves the
        # incident open: other target types may still be inbound.
        if parsed.clear_scope is None:
            await end_active_incidents(session, when)
        # Surface the all-clear itself in the feed (a status-only broadcast is
        # invisible there) as a notice — the operator wants to SEE "відбій".
        notice = await _make_notice(session, "clear", parsed, source_id, when)
        await done()
        return [Broadcast("status", t) for t in closed] + [Broadcast("notice", notice=notice)]

    # 2a-bis. "Дорозвідка" — ППО temporarily has no targets of the stated type
    # (or, if unstated, none at all): a real stand-down signal, not a
    # confirmed all-clear. Type-scoped when a type is named, else every open
    # track. Each closed track gets its own event (inheriting that track's
    # last known district) so the message is visible in the feed/track-inspect
    # view instead of vanishing as a bare status broadcast.
    if parsed.lost_signal:
        target = parsed.target_type if parsed.target_type != "unknown" else None
        closed = await close_all_active(session, when, target_type=target)
        pairs: list[tuple[Threat, ThreatEvent | None]] = []
        for t in closed:
            hit = _last_district_hit(t)
            ev = None
            if hit is not None:
                ev = _make_event(t.id, parsed, hit, source_id, message_id,
                                 forwarded_from_id, when, decision_source,
                                 reply_to_message_id, target_count=t.target_count)
                session.add(ev)
            pairs.append((t, ev))
        if any(ev is not None for _, ev in pairs):
            await session.commit()
            for t, ev in pairs:
                if ev is not None:
                    await apply_fusion(session, t)
        await done()
        return [Broadcast("event" if ev is not None else "status", t, ev) for t, ev in pairs]

    # 2a-ter. Terse target/launch pulse ("Ціль!", "Ще вихід", "3 ракети") — acted
    #     on ONLY while a city-wide alert is already open: a spotter calling the
    #     salvo in as it arrives. It corroborates that alert (an event on the
    #     sentinel district) and bumps the stated count. With no open city alert
    #     it's too terse to localize and falls through to the not-matched drop.
    if parsed.target_pulse:
        city = await find_open_citywide(session, when)
        did = await _citywide_did(session) if city is not None else None
        if city is not None and did is not None:
            city.target_type = _upgrade_type(city.target_type, parsed.target_type)
            if parsed.target_count and parsed.target_count > city.target_count:
                city.target_count = parsed.target_count
            ev = ThreatEvent(
                threat_id=city.id, district_id=did, raw_text=parsed.raw_text,
                event_time=when, confidence=parsed.confidence, decision_source=decision_source,
                source_id=source_id, source_message_id=message_id,
                forwarded_from_id=forwarded_from_id, reply_to_message_id=reply_to_message_id,
                event_target_type=parsed.target_type, event_target_count=city.target_count,
            )
            session.add(ev)
            await session.commit()
            await apply_fusion(session, city)
            await attach_to_incident(session, city, when)
            await done()
            return [Broadcast("event", city, ev)]

    # 2a-quater. Retrospective attack summary ("Загалом ... 8 балістичних С-400")
    #     — info, not a live target: no map threat, but surfaced in the feed as a
    #     notice so the operator sees the tally of the attack.
    if parsed.summary:
        notice = await _make_notice(session, "summary", parsed, source_id, when)
        await done()
        return [Broadcast("notice", notice=notice)]

    # 2b. Nothing localizable/actionable — keep the raw row, emit nothing.
    if not parsed.matched:
        await done()
        return []

    # 2c. Destroyed closes the matching open track. A "Мінус"-style reply names
    #     its target's chain directly; otherwise prefer the track over the named
    #     district, not merely the newest (see find_open_track).
    if parsed.status == "destroyed":
        track = await find_track_by_reply(session, source_id, reply_to_message_id)
        if track is None:
            prefer = {h.district_id for h in parsed.districts} or None
            track = await find_open_track(session, when, prefer_districts=prefer)
        if track is None:
            await done()
            return []
        # A closing message often names no district of its own ("Один збили,
        # залишився ще один") — inherit the track's last known position so the
        # message still becomes a real event (visible in the feed and in a
        # track's inspect view), instead of silently vanishing with only a
        # status-only broadcast the feed never displays.
        hit = parsed.districts[0] if parsed.districts else _last_district_hit(track)
        ev = None
        if hit is not None:
            ev = _make_event(track.id, parsed, hit, source_id,
                             message_id, forwarded_from_id, when, decision_source,
                             reply_to_message_id, target_count=track.target_count)
            session.add(ev)
        track.status = "destroyed"
        track.closed_at = when
        await session.commit()
        await apply_fusion(session, track)
        await done()
        # "event" (not "status") whenever we actually created one, so the
        # frontend feed (which only appends 'event' broadcasts) shows it —
        # a status-only broadcast is silently invisible there.
        return [Broadcast("event" if ev is not None else "status", track, ev)]

    # 2c-bis. Impact / confirmed strike location ("влучання по будівлі в
    #     Дніпровському районі", "у Святошинському... пошкоджено будівлю"). This
    #     is a HIT, not an active inbound target — record it as its own terminal
    #     marker (closed immediately) so it persists on the map as a distinct
    #     impact pin and appears in the feed, without being mistaken for a
    #     target still in the air or absorbing later sightings over that
    #     district. Being closed, it's invisible to all track continuation/
    #     closure logic (which all filter closed_at IS NULL). Target type is
    #     whatever this message stated or inherited (often ballistic mid-attack).
    if parsed.impact:
        # Dedup: a recent impact over the SAME district is the SAME strike (two
        # sources, one hit) — corroborate that marker instead of stacking a
        # second pin on the identical point. Else a fresh impact marker.
        track = await find_recent_impact(session, parsed.districts[0].district_id, when)
        if track is None:
            track = Threat(
                target_type=parsed.target_type,
                status="impact",
                target_count=parsed.target_count or 1,
                closed_at=when,
            )
            session.add(track)
            await session.commit()
        else:
            track.target_type = _upgrade_type(track.target_type, parsed.target_type)
        impacts: list[Broadcast] = []
        for hit in parsed.districts:
            ev = _make_event(track.id, parsed, hit, source_id, message_id,
                             forwarded_from_id, when, decision_source, reply_to_message_id,
                             target_count=track.target_count)
            session.add(ev)
            await session.commit()
            await apply_fusion(session, track)
            impacts.append(Broadcast("event", track, ev))
        await attach_to_incident(session, track, when)
        await done()
        return impacts

    # 2c-ter. City-wide threat ("Ціль на місто!", "Балістика на Київ") — a
    #     strike aimed at the city as a whole that no spotter has localized to a
    #     raion (the sub-minute ballistic phase, when the map would otherwise be
    #     empty). Raise ONE city-level alert: continue an open one (repeated
    #     callouts corroborate it) or start a fresh one. Its event attaches to
    #     the sentinel district so it has a valid point; the frontend renders it
    #     as a banner, not a pin. Type upgrades like a normal track, so a bare
    #     "на місто" after "Балістика!" inherits ballistic (see type inheritance).
    if parsed.citywide:
        did = await _citywide_did(session)
        if did is None:  # sentinel not seeded (shouldn't happen post-startup) — skip
            await done()
            return []
        track = await find_open_citywide(session, when)
        if track is None:
            track = Threat(target_type=parsed.target_type, status=_threat_status_for(parsed),
                           target_count=parsed.target_count or 1, scope="city")
            session.add(track)
            await session.commit()
        else:
            track.target_type = _upgrade_type(track.target_type, parsed.target_type)
            if parsed.status != "unconfirmed":
                track.status = "tracking"
            if parsed.target_count and parsed.target_count > track.target_count:
                track.target_count = parsed.target_count
        ev = ThreatEvent(
            threat_id=track.id, district_id=did, raw_text=parsed.raw_text,
            event_time=when, confidence=parsed.confidence, decision_source=decision_source,
            source_id=source_id, source_message_id=message_id,
            forwarded_from_id=forwarded_from_id, reply_to_message_id=reply_to_message_id,
            event_target_type=parsed.target_type, event_target_count=track.target_count,
        )
        session.add(ev)
        await session.commit()
        await apply_fusion(session, track)
        await attach_to_incident(session, track, when)
        await done()
        return [Broadcast("event", track, ev)]

    # 2d. Sighting / confirmed / unconfirmed -> continue or start a track.
    #     (1) reply to an OPEN chain = authoritative same-target signal (beats
    #     is_new_target); (2) else corroboration — continue only a track recently
    #     over the same district; (3) else a new track. A reply into a CLOSED
    #     chain falls through to (2)/(3), so it won't glue onto the newest track.
    track = await find_track_by_reply(session, source_id, reply_to_message_id)
    if track is None and not parsed.is_new_target:
        district_ids = {h.district_id for h in parsed.districts}
        track = await find_corroborating_track(session, when, district_ids)
    if track is None:
        track = Threat(target_type=parsed.target_type, status=_threat_status_for(parsed),
                       target_count=parsed.target_count or 1)
        session.add(track)
        await session.commit()
    else:
        track.target_type = _upgrade_type(track.target_type, parsed.target_type)
        if parsed.status != "unconfirmed":
            track.status = "tracking"
        # Group size only grows within a chain (2х -> "їх вже 3х").
        if parsed.target_count and parsed.target_count > track.target_count:
            track.target_count = parsed.target_count

    broadcasts: list[Broadcast] = []
    # One event per mentioned district, in movement order.
    for hit in parsed.districts:
        ev = _make_event(track.id, parsed, hit, source_id, message_id,
                         forwarded_from_id, when, decision_source, reply_to_message_id,
                         target_count=track.target_count)
        session.add(ev)
        await session.commit()
        await apply_fusion(session, track)
        broadcasts.append(Broadcast("event", track, ev))

    await attach_to_incident(session, track, when)
    await done()
    return broadcasts


async def _make_notice(session, kind: str, parsed: ParseResult, source_id: int | None,
                        when: datetime) -> Notice:
    notice = Notice(kind=kind, text=parsed.raw_text, target_type=parsed.target_type,
                    source_id=source_id, event_time=when)
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
                target_count: int = 1) -> ThreatEvent:
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
        reply_to_message_id=reply_to_message_id,
        event_target_type=parsed.target_type,
        event_target_count=target_count,
    )

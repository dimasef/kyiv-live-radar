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
from datetime import datetime

from sqlalchemy import select

from .config import settings
from .parser import DistrictHit, DistrictMatcher, ParseResult, normalize, parse_message
from .models import RawMessage, Threat, ThreatEvent
from .tracking import (
    apply_fusion,
    close_all_active,
    find_corroborating_track,
    find_open_track,
    find_track_by_reply,
)

# Serialize ingestion: concurrent inbound messages sharing one open track would
# otherwise race (split tracks, wrong corroboration, SQLite "database is locked").
# Single-instance MVP — one lock is enough; multi-instance would move to the DB.
_ingest_lock = asyncio.Lock()


@dataclass
class Broadcast:
    type: str  # 'event' | 'status'
    threat: Threat
    event: ThreatEvent | None = None


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
        if llm is not None and (llm.districts or llm.status in ("clear", "destroyed")):
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

    async def done() -> None:
        raw.processed = True
        await session.commit()

    # 2a. All-clear closes every open track.
    if parsed.status == "clear":
        closed = await close_all_active(session, when)
        await done()
        return [Broadcast("status", t) for t in closed]

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
                                 reply_to_message_id)
                session.add(ev)
            pairs.append((t, ev))
        if any(ev is not None for _, ev in pairs):
            await session.commit()
            for t, ev in pairs:
                if ev is not None:
                    await apply_fusion(session, t)
        await done()
        return [Broadcast("event" if ev is not None else "status", t, ev) for t, ev in pairs]

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
                             reply_to_message_id)
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
        if track.target_type == "unknown" and parsed.target_type != "unknown":
            track.target_type = parsed.target_type
        if parsed.status != "unconfirmed":
            track.status = "tracking"
        # Group size only grows within a chain (2х -> "їх вже 3х").
        if parsed.target_count and parsed.target_count > track.target_count:
            track.target_count = parsed.target_count

    broadcasts: list[Broadcast] = []
    # One event per mentioned district, in movement order.
    for hit in parsed.districts:
        ev = _make_event(track.id, parsed, hit, source_id, message_id,
                         forwarded_from_id, when, decision_source, reply_to_message_id)
        session.add(ev)
        await session.commit()
        await apply_fusion(session, track)
        broadcasts.append(Broadcast("event", track, ev))

    await done()
    return broadcasts


def _last_district_hit(track: Threat) -> DistrictHit | None:
    """Synthesize a hit for the track's most recently reported district, for a
    closing message that names no district of its own."""
    if not track.events:
        return None
    last = max(track.events, key=lambda e: e.event_time)
    return DistrictHit(district_id=last.district_id, name="", position=0)


def _make_event(threat_id, parsed: ParseResult, hit, source_id, message_id,
                forwarded_from_id, when: datetime, decision_source: str,
                reply_to_message_id: int | None = None) -> ThreatEvent:
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
    )

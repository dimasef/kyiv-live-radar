"""Per-pass ingest context (`IngestContext`) plus the pure helpers around target
type: cross-message inheritance (`_note_and_inherit_type`) and the shared
start/continue-a-track bits (`_new_track` / `_apply_update`)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ...config import settings
from ...domain.lifecycle import promote_track
from ...domain.target_types import upgrade_type
from ...feeds.common import build_region_matchers
from ...models import HOME_REGION, RawMessage, Threat, utcnow
from ...parsing import ParseResult, normalize
from ...parsing.vocab import _MISSILE_CARRIER, _MISSILE_NAMED, _MISSILE_WEAPON
from ...timeutil import naive

# Per-source "last stated target type" context for cross-message type
# inheritance (see settings.type_inherit_window_minutes). Keyed by source_id ->
# (target_type, when). In-memory and order-dependent, which is fine: ingestion
# is serialized and every feed path (live, replay, reprocess) presents messages
# in chronological order per source. A process restart drops it, which is why
# `rehydrate_type_context` replays the recent window on startup — with a 30-min
# per-source window a deploy mid-wave used to cost half an hour of typing.
# Rule-only: mutating an already-districted message's type never adds an LLM
# call, since should_fallback short-circuits to False whenever districts exist.
_recent_type: dict[int, tuple[str, datetime]] = {}


def is_late(when: datetime) -> bool:
    """True when a message reached us more than a stale-window after it was
    posted — i.e. a reconnect backfill replaying history, not live traffic.

    Anything such a message would OPEN is already dead on arrival: the sweeper
    closes a track born outside that window on its next tick (the same
    reasoning triage.py::route_verdict uses to drop a late rescue). What it
    would CLOSE is still valid, which is why callers gate on the ACTION, not on
    this alone. Shared by the spotter dispatch and the alert-channel ingest,
    where an out-of-order start opened a phantom alert that hung for two hours
    (2026-07-31, alert 39)."""
    return (naive(utcnow()) - naive(when)).total_seconds() / 60.0 > settings.track_stale_minutes


def _carrier_only(parsed: ParseResult) -> bool:
    """Whether this message is `missile` purely because it names a Ту-95/160 or
    "стратегічна авіація", with no weapon of its own (see _MISSILE_CARRIER)."""
    if parsed.target_type != "missile":
        return False
    norm = normalize(parsed.raw_text)
    return (any(c in norm for c in _MISSILE_CARRIER)
            and not any(w in norm for w in _MISSILE_WEAPON))


def _names_cruise_weapon(parsed: ParseResult) -> bool:
    """Whether the message names a cruise weapon outright ("Калібри", "крилаті",
    "Х-101") rather than the ambiguous generic "ракета" (see _MISSILE_NAMED)."""
    return any(w in normalize(parsed.raw_text) for w in _MISSILE_NAMED)


def _note_and_inherit_type(
    parsed: ParseResult,
    source_id: int | None,
    when: datetime,
    window_minutes: int | None = None,
) -> None:
    """Record this message's stated type, or inherit a recent one onto a
    district-bearing message that stated none. Mutates `parsed.target_type`.

    `window_minutes` is the reporting channel's own window (Source.
    type_inherit_minutes); None falls back to the global default. Passed in
    rather than looked up here so this stays a pure function — the caller owns
    the DB."""
    if source_id is None:  # no channel identity (e.g. simulator) — no context
        return
    # Conversational/meta chatter mentions types without being about a live
    # target — a donation post's "до останнього Шахеда та ракети", a recap, a
    # quoted official — and on 07-18 such a mention poisoned a channel's
    # context mid-salvo. These classes neither record nor consume a type.
    if (parsed.promo or parsed.ad_action or parsed.political_quote
            or parsed.civic_notice or parsed.eppo_marks or parsed.siren_only
            or parsed.negated or parsed.summary or parsed.day_recap
            or parsed.chatter):
        return
    # Same reasoning, one step earlier in the attack: a message typed only by
    # the CARRIER ("З оленя злетіли тушки") is about bombers hours from their
    # launch lines, so it must not claim the channel is now calling cruise
    # missiles. It surfaces as its own forecast notice; what it must not do is
    # retype the bare toponym a spotter shouts 30 seconds later — live
    # 2026-08-19 21:11, where that toponym belonged to a ballistic salvo
    # running at the same time.
    if _carrier_only(parsed):
        return
    # And the same again for a wave that has not arrived: "Найближчим часом
    # можлива повторна хвиля балістики" is about what MIGHT come, not what is in
    # the sky. Live 2026-08-19 22:18-22:20, two such posts (one per channel) set
    # both channels to ballistic, and every Kalibr callout for the next nine
    # minutes — Богуслав, Тараща, «Група КР на Богуслав» — inherited it.
    if parsed.anticipated:
        return
    if parsed.target_type != "unknown":
        # "missile" is the generic parent of the specific "ballistic": during a
        # ballistic salvo a spotter often drops a bare "3 ракети" between the
        # toponym callouts, which must NOT downgrade a still-fresh ballistic
        # context to generic missile. Any OTHER type (shahed/jet, or ballistic
        # itself) is a real change and overwrites normally. Time is refreshed
        # either way so the ongoing attack keeps the context alive.
        #
        # A NAMED cruise weapon is the exception: "6 калібрів звернули на
        # Черкащину" identifies what is flying as precisely as "балістика" does,
        # so it must be able to correct the context rather than be swallowed by
        # it. Same night, 22:22: both channels said «Калібри» and both stayed
        # ballistic, because the guard could not tell them from a bare "ракети".
        prev = _recent_type.get(source_id)
        if (
            parsed.target_type == "missile"
            and not _names_cruise_weapon(parsed)
            and prev is not None
            and prev[0] == "ballistic"
            and _within_inherit_window(when, prev[1], window_minutes)
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
    if _within_inherit_window(when, rwhen, window_minutes):
        parsed.target_type = rtype


async def rehydrate_type_context(session) -> int:
    """Rebuild `_recent_type` from stored messages, on startup.

    The context is in-memory, so every restart drops it — and with a per-source
    window that can now be 30 minutes, a deploy mid-wave costs half an hour of
    typing instead of five minutes. Live case, 2026-08-21: «Новий реактивний з
    Брянської» at 16:49 correctly typed the callouts at 16:51, 16:57 and 17:01,
    then the process restarted and everything from 17:11 on went back to
    `unknown` — 22 minutes into a 30-minute window.

    Replays each channel's recent messages through `_note_and_inherit_type`
    itself rather than re-deriving "the last type stated": that keeps every rule
    identical — the suppressor skips, the carrier-only veto, the
    ballistic-over-generic-missile guard. The ParseResult it mutates is thrown
    away; only the recorded context survives. Read-only, no events, no LLM.

    Returns the number of channels whose context was restored.
    """
    from sqlalchemy import select

    from ...models import RawMessage, Source
    from ...parsing import parse_message
    from ..lock import ingest_lock

    sources = {
        s.id: s for s in await session.scalars(select(Source).where(Source.role == "spotter"))
    }
    if not sources:
        return 0
    windows = {
        sid: (s.type_inherit_minutes
              if s.type_inherit_minutes is not None
              else settings.type_inherit_window_minutes)
        for sid, s in sources.items()
    }
    lookback = max(windows.values(), default=0)
    if lookback <= 0:
        return 0
    since = naive(utcnow()) - timedelta(minutes=lookback)
    rows = list(
        await session.scalars(
            select(RawMessage)
            .where(RawMessage.source_id.in_(sources), RawMessage.event_time >= since)
            .order_by(RawMessage.event_time)
        )
    )
    if not rows:
        return 0
    matcher = await build_region_matchers(session)
    # Under the same lock the live path takes: startup and the first inbound
    # message would otherwise both write `_recent_type`, and a half-replayed
    # context is worse than none.
    async with ingest_lock:
        for raw in rows:
            region = sources[raw.source_id].region
            parsed = parse_message(raw.text or "", matcher.for_region(region))
            _note_and_inherit_type(parsed, raw.source_id, raw.event_time, windows[raw.source_id])
    return len({sid for sid in _recent_type if sid in sources})


def _within_inherit_window(a: datetime, b: datetime, window_minutes: int | None = None) -> bool:
    """Whether `a` and `b` are within the type-inheritance window. Drops tzinfo
    first so SQLite-naive and aware datetimes compare (all values are UTC)."""
    an = a.replace(tzinfo=None) if a.tzinfo is not None else a
    bn = b.replace(tzinfo=None) if b.tzinfo is not None else b
    minutes = window_minutes if window_minutes is not None else settings.type_inherit_window_minutes
    return abs((an - bn).total_seconds()) <= timedelta(minutes=minutes).total_seconds()


def _threat_status_for(parsed: ParseResult) -> str:
    if parsed.status == "unconfirmed":
        return "unconfirmed"
    return "tracking"


def _new_track(parsed: ParseResult, when: datetime, **overrides) -> Threat:
    """A fresh Threat from a parsed sighting. `overrides` set what differs per
    handler — `scope="city"` for a city-wide alert, or a fixed `target_count=1`
    for a multi-target enumeration (each district is one target; the stated group
    size there is the whole-salvo total, not per-raion)."""
    fields: dict = {
        "target_type": parsed.target_type,
        "status": _threat_status_for(parsed),
        "target_count": parsed.target_count or 1,
        "created_at": when,
    }
    fields.update(overrides)
    return Threat(**fields)


def _apply_update(parsed: ParseResult, track: Threat, *, promote: bool = True,
                  grow_count: bool = True) -> None:
    """Fold a new corroborating event into an existing track: upgrade the type
    (unknown→stated, missile→ballistic), promote out of 'unconfirmed' on a
    confirmed status, and grow the group count. `promote`/`grow_count` are turned
    off for the paths that intentionally skip them — a terse pulse never promotes,
    and a multi-target enumeration counts per district, not by the stated total."""
    track.target_type = upgrade_type(track.target_type, parsed.target_type)
    if promote and parsed.status != "unconfirmed":
        promote_track(track)
    if grow_count and parsed.target_count and parsed.target_count > track.target_count:
        track.target_count = parsed.target_count


@dataclass
class IngestContext:
    """Groups the parameters every process_parsed handler needs — not a plugin
    framework, just avoids re-threading nine positional args through each handler
    signature."""

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
    # True when parsed.target_type was INFERRED from the surrounding picture —
    # the open incident's dominant type (tier 2) or the LLM's read of the recent
    # feed (tier 4) — rather than stated by the message or its own channel's
    # last typed post. The ballistic enumeration split must not trust it: on a
    # mixed drone+ballistic night the wider picture reads "ballistic" and would
    # wrongly split a meandering drone's «Троя/Воскресенка» enumeration.
    type_inferred: bool = False
    # Whether this message's AGE may veto it (see handlers._dispatch). Only the
    # live Telegram path sets it: replay and reprocess deliberately re-run old
    # messages at their own timestamps, where every message is "old" and the
    # gate would drop the entire corpus.
    enforce_age: bool = False
    # Which track pool this message acts on (domain/districts.resolve_region):
    # the region of the LAST district it named, else the reporting channel's own
    # region. Everything that finds or closes a track is scoped by it.
    region: str = HOME_REGION
    # {district_id: region} for the whole gazetteer — a multi-district message
    # can straddle the oblast border, and _handle_multi_targets opens one track
    # per district, each in its own pool.
    region_by_id: dict[int, str] = field(default_factory=dict)

    def arrived_late(self) -> bool:
        return self.enforce_age and is_late(self.when)

    def region_of(self, district_id: int) -> str:
        return self.region_by_id.get(district_id, self.region)

    async def done(self) -> None:
        self.raw.processed = True
        await self.session.commit()

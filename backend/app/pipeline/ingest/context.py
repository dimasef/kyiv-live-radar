"""Per-pass ingest context (`IngestContext`) plus the pure helpers around target
type: cross-message inheritance (`_note_and_inherit_type`) and the shared
start/continue-a-track bits (`_new_track` / `_apply_update`)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import NamedTuple

from ...config import settings
from ...domain.lifecycle import promote_track
from ...domain.target_types import upgrade_type
from ...feeds.common import build_region_matchers
from ...models import HOME_REGION, RawMessage, Threat, utcnow
from ...parsing import ParseResult, normalize
from ...parsing.vocab import _MISSILE_CARRIER, _MISSILE_NAMED, _MISSILE_WEAPON
from ...timeutil import naive


class TypeContext(NamedTuple):
    """One channel's current target type. A NamedTuple rather than a dataclass so
    the long-standing `_recent_type[sid][0]` indexing keeps working.

    `inferred` marks a type nobody wrote down — the LLM classifier read it off
    the surrounding feed. It rides along so a message that INHERITS such a type
    can still be told apart from one whose own channel stated it: the ballistic
    enumeration split (handlers._handle_sighting) must not treat a guess as
    grounds for splitting «Вишневе Жуляни» into two targets. An OPERATOR retype
    is not inferred — a human correcting the map outranks the rules.
    """

    target_type: str
    when: datetime
    inferred: bool = False


# Per-source "last known target type" context for cross-message type
# inheritance (see settings.type_inherit_window_minutes). In-memory and
# order-dependent, which is fine: ingestion is serialized and every feed path
# (live, replay, reprocess) presents messages in chronological order per source.
# A process restart drops it, which is why `rehydrate_type_context` replays the
# recent window on startup — with a 30-min per-source window a deploy mid-wave
# used to cost half an hour of typing.
# Rule-only: mutating an already-districted message's type never adds an LLM
# call, since should_fallback short-circuits to False whenever districts exist.
_recent_type: dict[int, TypeContext] = {}

# Channels whose last classifier call came back "I can't tell", as
# source_id -> (when, feed generation at that moment). A decline is an ANSWER
# about the current sky, and re-asking while the sky picture is unchanged buys
# the same answer again: on 2026-08-23 18:40-18:41 the northern channel bought
# three identical `unknown`/`none` verdicts in fifty seconds ($0.0058) across
# three different toponyms. See `type_context_declined` for what un-declines it.
_declined_type: dict[int, tuple[datetime, int]] = {}

# Bumped every time a message STATES a type (see _note_and_inherit_type) or an
# operator corrects one. Not bumped by the classifier's own verdict: the
# classifier reads `raw_messages` text (type_context.build_type_context), and a
# verdict is not a message — it changes nothing about what the next call sees.
_type_generation: int = 0


def reset_type_context() -> None:
    """Drop every in-memory type-context global. Tests build a fresh DB per case,
    so a value cached from a prior one would leak in as a spurious inherited type
    or a spurious decline."""
    global _type_generation
    _recent_type.clear()
    _declined_type.clear()
    _type_generation = 0


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
) -> bool:
    """Record this message's stated type, or inherit a recent one onto a
    district-bearing message that stated none. Mutates `parsed.target_type`.

    Returns whether the type it INHERITED was itself inferred (see TypeContext),
    so the caller can fold that into IngestContext.type_inferred. False whenever
    nothing was inherited.

    `window_minutes` is the reporting channel's own window (Source.
    type_inherit_minutes); None falls back to the global default. Passed in
    rather than looked up here so this stays a pure function — the caller owns
    the DB."""
    if source_id is None:  # no channel identity (e.g. simulator) — no context
        return False
    # Conversational/meta chatter mentions types without being about a live
    # target — a donation post's "до останнього Шахеда та ракети", a recap, a
    # quoted official — and on 07-18 such a mention poisoned a channel's
    # context mid-salvo. These classes neither record nor consume a type.
    if (parsed.promo or parsed.ad_action or parsed.political_quote
            or parsed.civic_notice or parsed.eppo_marks or parsed.siren_only
            or parsed.negated or parsed.summary or parsed.day_recap
            or parsed.chatter):
        return False
    # Same reasoning, one step earlier in the attack: a message typed only by
    # the CARRIER ("З оленя злетіли тушки") is about bombers hours from their
    # launch lines, so it must not claim the channel is now calling cruise
    # missiles. It surfaces as its own forecast notice; what it must not do is
    # retype the bare toponym a spotter shouts 30 seconds later — live
    # 2026-08-19 21:11, where that toponym belonged to a ballistic salvo
    # running at the same time.
    if _carrier_only(parsed):
        return False
    # And the same again for a wave that has not arrived: "Найближчим часом
    # можлива повторна хвиля балістики" is about what MIGHT come, not what is in
    # the sky. Live 2026-08-19 22:18-22:20, two such posts (one per channel) set
    # both channels to ballistic, and every Kalibr callout for the next nine
    # minutes — Богуслав, Тараща, «Група КР на Богуслав» — inherited it.
    if parsed.anticipated:
        return False
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
        global _type_generation
        prev = _recent_type.get(source_id)
        if (
            parsed.target_type == "missile"
            and not _names_cruise_weapon(parsed)
            and prev is not None
            and prev[0] == "ballistic"
            and _within_inherit_window(when, prev[1], window_minutes)
        ):
            _recent_type[source_id] = TypeContext("ballistic", when)
        else:
            _recent_type[source_id] = TypeContext(parsed.target_type, when)
        # A stated type is new information in the FEED — every channel's stale
        # "I can't tell" is now worth re-asking (see type_context_declined).
        _type_generation += 1
        return False
    # Untyped: inherit only when the message is a real (localizable or
    # city-wide) sighting — a bare "Троя" or "Ціль на місто!" between typed
    # posts — AND a recent stated type exists for this same channel.
    if not parsed.districts and not parsed.citywide:
        return False
    recent = _recent_type.get(source_id)
    if recent is None:
        return False
    if not _within_inherit_window(when, recent.when, window_minutes):
        return False
    parsed.target_type = recent.target_type
    return recent.inferred


def note_inferred_type(source_id: int | None, target_type: str, when: datetime) -> None:
    """Record a type the LLM classifier read off the feed as this channel's
    current context, so the NEXT bare toponym inherits it instead of paying for
    the same answer again.

    Without this the fourth tier was per-message: on 2026-08-23 one loitering
    jet drone over Новгород-Сіверський cost three identical calls in twelve
    minutes (16:35, 16:40, 16:47 — all jet_drone/0.85/context), because the
    verdict mutated only that message's ParseResult and the channel context
    stayed as stale as it was before the call. Replayed over five days of stored
    messages (2 453 localizable sightings, classifier hit-rate 41% as measured
    by eval/type_eval), feeding it back cuts type calls 845 -> 435 AND raises
    typed coverage 80.6% -> 90.0%: the inherited verdict also types the
    sightings a call would have answered `unknown` on.

    Decay is bounded to ONE window per answer, not a self-refreshing chain —
    inheritance deliberately never touches the stored timestamp, so a verdict
    recorded at 16:35 stops being inherited at 17:05 whatever happens in
    between. `inferred=True` keeps it distinguishable downstream.
    """
    if source_id is None or target_type == "unknown":
        return
    _recent_type[source_id] = TypeContext(target_type, when, inferred=True)


def note_operator_type(source_ids, target_type: str, when: datetime) -> None:
    """Record an operator's /admin retype as the current type of every channel
    that reported the corrected track.

    A human looking at the map is the most authoritative type signal the system
    has — above the rules, and far above the classifier's read of the feed. It
    was also the only one that went nowhere: `admin_retype_threat` fixed the
    track and filed a ParserCorrection, and the live context carried on as
    though nothing had been said. Live 2026-08-23: the operator retyped track
    1279 to jet_drone at 18:50:12.7, and 5.7 seconds later the next callout paid
    $0.002 to be told `shahed` — which then became the channel context, because
    the classifier's guess seeds it (note_inferred_type) and the correction did
    not.

    ALL contributing channels, not just the latest: they were all describing the
    one target the operator just relabelled, and the cross-channel case is
    exactly the gap the classifier exists to fill. `inferred=False` — this is a
    stated type, so the ballistic enumeration split may trust it.

    Callers must pass only an OPEN track's channels: retyping a closed track is
    a history correction, and injecting yesterday's type into today's live
    context is the poisoning this module spends most of its rules preventing.

    Called from an /admin request rather than from ingest, so it runs outside
    `ingest_lock` — deliberately. There is no await here, so on the single event
    loop this whole function is atomic against a concurrent ingest pass; the lock
    exists for multi-step DB mutation (see rehydrate_type_context), which this
    is not.
    """
    global _type_generation
    if target_type == "unknown":
        return
    for source_id in {s for s in source_ids if s is not None}:
        _recent_type[source_id] = TypeContext(target_type, when)
        _declined_type.pop(source_id, None)
    _type_generation += 1


def note_type_decline(source_id: int | None, when: datetime) -> None:
    """Remember that the classifier looked at the feed and could not tell."""
    if source_id is None:
        return
    _declined_type[source_id] = (when, _type_generation)


def type_context_declined(source_id: int | None, when: datetime,
                          window_minutes: int | None = None) -> bool:
    """Whether asking the classifier again would just re-buy a recent decline.

    True only while BOTH hold: the decline is inside this channel's inheritance
    window, and no message has stated a type anywhere since (`_type_generation`).
    That second condition is what makes a window as long as 30 minutes safe —
    the thing that would change the answer is a wave being announced, and an
    announcement is precisely a stated type. A run of bare toponyms, which is
    what the northern channel emits for most of a night, changes nothing the
    classifier is told to read.

    A LOW-CONFIDENCE verdict is deliberately not a decline (see
    TypeVerdict.usable): «Новгород з півночі» scored shahed 0.65 at 18:49:31 and
    the next call 37 seconds later scored 0.75 and was applied. Only an explicit
    `unknown`/`evidence=none` counts, and a call that never returned counts as
    nothing at all — that is a failure, not an answer.
    """
    if source_id is None:
        return False
    entry = _declined_type.get(source_id)
    if entry is None:
        return False
    declined_at, generation = entry
    if generation != _type_generation:
        return False
    return _within_inherit_window(when, declined_at, window_minutes)


def _stored_llm_type(raw) -> str | None:
    """The type verdict stored on a raw message, if it was one we would apply.
    Mirrors `_maybe_llm_type`'s replay branch so a rehydrate restores the same
    context the live pass established — including its mode check, so verdicts
    banked during a SHADOW night can't start steering the map the moment the
    process restarts in live mode."""
    if raw.llm_type is None or settings.llm_type_mode != "live":
        return None
    from ...parsing.type_llm import normalize_type_verdict

    verdict = normalize_type_verdict({
        "target_type": raw.llm_type, "evidence": raw.llm_type_evidence,
        "confidence": raw.llm_type_confidence or 0.0,
    })
    return verdict.target_type if verdict.usable else None


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
    away; only the recorded context survives. Read-only, no events, no LLM: a
    STORED classifier verdict is replayed through `note_inferred_type`, so a
    restart doesn't throw away a type we already paid for and start paying for
    it again message by message.

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
            # Same order as the live pass: the classifier is the LAST tier, so
            # its verdict only lands where the rules and the channel window
            # left the message untyped.
            if parsed.target_type == "unknown":
                stored = _stored_llm_type(raw)
                if stored is not None:
                    note_inferred_type(raw.source_id, stored, raw.event_time)
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

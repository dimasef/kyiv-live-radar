"""Ingest pipeline entry points + orchestration. `ingest_message` is the
serialized live entry (shared by the Telethon listener and the simulator);
`process_parsed` is the reusable resolve->track->fuse half, also driven by
`scripts/reprocess_raw.py` and `process_rescued`."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from ...config import settings
from ...domain.districts import district_regions, resolve_region
from ...domain.incidents import find_active_incident, incident_type_prior
from ...domain.target_types import type_plausible_in
from ...models import RawMessage, Source
from ...observability import ingest_span, metrics
from ...parsing import DistrictHit, DistrictMatcher, LlmUsage, ParseResult
from ..lock import ingest_lock
from ..results import Broadcast
from .context import (
    IngestContext,
    _note_and_inherit_type,
    note_inferred_type,
    note_type_decline,
    type_context_declined,
)
from .handlers import _dispatch, _handle_citywide, _handle_sighting, _ingest_outcome
from .resolve import _resolve, in_promo_thread
from .type_context import build_type_context, wants_llm_type


async def ingest_message(session, **kwargs) -> list[Broadcast]:
    """Serialized entry point — see _ingest_locked for the pipeline."""
    async with ingest_lock:
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
    enforce_age: bool = False,
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
        enforce_age=enforce_age,
    )


def _apply_llm_to_raw(raw: RawMessage, attempted: bool, usage: LlmUsage | None,
                      response: dict | None) -> None:
    """Stamp the LLM call's outcome (attempt flag, token cost, full response) onto
    the raw row for /raw audit — independent of whether its districts were used.
    Leaves llm_response untouched when the call didn't complete, so a reprocess
    that doesn't re-invoke the LLM keeps the STORED verdict for replay."""
    raw.llm_attempted = attempted
    if usage is not None:
        raw.llm_input_tokens = usage.input_tokens
        raw.llm_output_tokens = usage.output_tokens
        raw.llm_cost_usd = usage.cost_usd
    if response is not None:
        raw.llm_response = response


async def _source_settings(session, source_id: int | None) -> tuple[bool, int | None]:
    """This channel's per-source pipeline knobs: (may it use the LLM step, its
    type-inheritance window — None for the global default).

    A primary-key get per message, which is free enough here: ingestion is
    serialized behind one lock, so there is no concurrency to amortize over, and
    reading it live means an operator's change in /admin takes effect on the
    next message instead of at the next restart. SQLAlchemy's identity map
    usually answers it from the session anyway.

    A message with no source row (the simulator, a test) keeps the LLM: the
    switch is something an operator turns OFF for a named channel, never a
    default that an absent row could silently apply."""
    if source_id is None:
        return True, None
    src = await session.get(Source, source_id)
    if src is None:
        return True, None
    return src.llm_enabled, src.type_inherit_minutes


async def _infer_incident_type(session, parsed: ParseResult, when: datetime,
                               region: str) -> bool:
    """Second-tier type fallback: a still-untyped sighting during a live attack
    takes the open incident's dominant type. The per-channel window
    (_note_and_inherit_type) is only 5 min and channel-scoped — during the 07-18
    toponym barrage («Нивки», «Обухів»…) it kept expiring while the OTHER channel
    shouted «балістика», leaving 12 tracks "unknown" mid-salvo. Mutates
    parsed.target_type and returns whether it did (the ballistic enumeration
    split must NOT trust an incident-derived type). A later explicitly-typed
    event that disagrees still surfaces as a fusion conflict."""
    if parsed.target_type != "unknown" or not (parsed.districts or parsed.citywide):
        return False
    # `region` is this message's own, so a northern sighting reads the northern
    # attack's type and not Kyiv's — the same rule that decides which track pool
    # it acts on. Resolved by the caller: the type tiers run before the context
    # is built, and all three of them need it.
    inc = await find_active_incident(session, when, region)
    prior = await incident_type_prior(session, inc, when) if inc is not None else None
    if prior is not None and type_plausible_in(prior, region):
        parsed.target_type = prior
        return True
    return False


async def _maybe_llm_type(session, raw: RawMessage, parsed: ParseResult, when: datetime,
                          *, allow_llm: bool, region: str, source_llm_enabled: bool = True,
                          window_minutes: int | None = None) -> str | None:
    """Fourth and last type tier: ask the LLM what is in the sky right now.

    Reached only when the message names a place, produced something to record,
    and the text, the per-channel window and the incident prior all said
    `unknown` — 46% of localizable sightings on the real corpus. Mutates
    parsed.target_type in 'live' mode and returns the applied type (None when
    nothing was applied), so the caller can mark the event's provenance.

    A STORED verdict is replayed rather than re-queried: that is what makes an
    admin reprocess of a whole night free, and it mirrors how the triage engine
    replays `llm_response`.

    `source_llm_enabled` (Source.llm_enabled) is the operator's per-channel
    switch and comes FIRST, ahead of the replay branch: a channel the operator
    took off the LLM must not have last week's stored verdicts re-applied to it
    by the next rebuild. `allow_llm` is the narrower spend gate — it stops a new
    call while leaving an already-paid-for verdict replayable.
    """
    if (settings.llm_type_mode == "off" or not source_llm_enabled
            or not wants_llm_type(parsed)):
        return None
    # Lazy like every other parsing.llm import: it pulls the anthropic client,
    # which the eval/reprocess tooling has no reason to load.
    from ...parsing.type_llm import normalize_type_verdict

    if raw.llm_type is not None:
        verdict = normalize_type_verdict({
            "target_type": raw.llm_type, "evidence": raw.llm_type_evidence,
            "confidence": raw.llm_type_confidence or 0.0,
        })
    else:
        # The promo-thread veto and the budget guard gate spend the same way
        # they gate the other two consumers — this is the highest-VOLUME of the
        # three (one call per untyped sighting, 267 on the busiest night in the
        # corpus), so it is the one a runaway would show up on first.
        # `llm_fallback_enabled` is the pipeline-wide "may we call the API at
        # all" switch, which is exactly what a `--no-llm` reprocess turns off:
        # without it, rebuilding a night of history would fire one live call per
        # untyped sighting instead of replaying the verdicts it already has.
        if not allow_llm or not settings.llm_fallback_enabled or not settings.anthropic_api_key:
            return None
        # This channel already asked and was told "I can't tell", and nothing has
        # stated a type in the feed since — the classifier would be reading the
        # same picture and giving the same answer. Three such repeats cost
        # $0.0058 in fifty seconds on 2026-08-23.
        if type_context_declined(raw.source_id, when, window_minutes):
            return None
        from ..triage import llm_spend_ok

        if not await llm_spend_ok():
            return None
        from ...parsing.type_llm import llm_target_type

        source = await session.get(Source, raw.source_id) if raw.source_id else None
        context = await build_type_context(session, when, exclude_raw_id=raw.id,
                                           region=region)
        # Stamped BEFORE the await, not after: llm_target_type swallows timeouts
        # and API errors into (None, None), so gating this on `usage` recorded
        # only the calls that SUCCEEDED. A timed-out call then looked byte-for-
        # byte like a call that was never made — same llm_attempted=0, same NULL
        # verdict, same $0 — and an analysis of the 2026-08-23 feed spent its
        # time hunting a config difference that did not exist. The field means
        # "we tried", which is exactly the thing /raw needs to show.
        raw.llm_attempted = True
        verdict, usage = await llm_target_type(
            parsed.raw_text, context, source.name if source is not None else "канал",
            region,
        )
        if usage is not None:
            # ACCUMULATE: the budget guard sums this column, and a message can
            # in principle have paid for an inline localization call too.
            raw.llm_input_tokens = (raw.llm_input_tokens or 0) + usage.input_tokens
            raw.llm_output_tokens = (raw.llm_output_tokens or 0) + usage.output_tokens
            raw.llm_cost_usd = (raw.llm_cost_usd or 0.0) + usage.cost_usd
        if verdict is None:
            return None
        raw.llm_type = verdict.target_type
        raw.llm_type_confidence = verdict.confidence
        raw.llm_type_evidence = verdict.evidence
    if verdict.declined:
        note_type_decline(raw.source_id, when)
        return None
    if settings.llm_type_mode != "live" or not verdict.usable:
        return None
    # The rail is applied to the ANSWER as well as to the schema, because a
    # STORED verdict takes the branch above without ever seeing the schema.
    if not type_plausible_in(verdict.target_type, region):
        return None
    parsed.target_type = verdict.target_type
    return verdict.target_type


async def _maybe_triage(ctx: IngestContext, triage: str, matcher: DistrictMatcher,
                        allow_llm: bool = True, source_llm_enabled: bool = True) -> list[Broadcast]:
    """Hand this message to the second-pass triage engine. 'live' enqueues a
    qualifying district-less/suppressed-but-threat-flavored message (reusing any
    inline LLM verdict — no second API call); 'replay' routes the STORED verdict
    inline for a deterministic reprocess. Marks the raw row so /raw shows where it
    went. Returns broadcasts from the replay path ([] for live/off).

    The triage imports are lazy: ingest and triage are mutually recursive (ingest
    enqueues to triage; triage's rescue calls back into process_rescued), so this
    direction stays in-function to keep the package importable without a cycle."""
    raw = ctx.raw
    # The operator's per-channel switch, same reach as in _maybe_llm_type: no
    # new job, and no replay of a stored verdict either.
    if not source_llm_enabled:
        return []
    if triage == "live":
        from ..triage import TriageJob, enqueue_job, should_triage

        # The triage engine is where most of the LLM spend actually happens (it
        # picks up the suppressed-but-threat-flavored classes the inline
        # fallback never sees), so the promo-thread veto has to reach it too —
        # gating only `_resolve` would have left the donation-thread arguments
        # billing exactly as before.
        if allow_llm and should_triage(ctx.parsed, ctx.decision_source, raw.llm_response):
            job = TriageJob(
                raw_id=raw.id, text=ctx.parsed.raw_text, when=ctx.when, source_id=ctx.source_id,
                message_id=ctx.message_id, reply_to_message_id=ctx.reply_to_message_id,
                forwarded_from_id=ctx.forwarded_from_id,
                forwarded_from_channel_id=ctx.forwarded_from_channel_id,
                verdict=raw.llm_response,
            )
            raw.triage_state = "pending" if enqueue_job(job) else "skipped"
        return []
    if triage == "replay" and raw.llm_response is not None:
        return await _replay_triage_verdict(ctx, raw.llm_response, matcher)
    return []


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
    enforce_age: bool = False,
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

    `enforce_age` lets a message's age veto anything it would OPEN (see
    IngestContext.arrived_late). Off by default so reprocess/replay — which
    legitimately re-run an entire old corpus — behave exactly as before; the
    live Telegram feed turns it on.
    """
    # One custom span per pass, parent to the auto-instrumented SQL/LLM child
    # spans. It carries the domain facts auto-instrumentation can't see —
    # decision_source, target_type, and the final outcome — so Logfire can answer
    # "how many messages/hour landed in dropped" or "what share of decisions came
    # from the LLM" by attribute filter, not log-text parsing. Dormant (no-op)
    # until observability is set up, so reprocess/eval/tests are unaffected.
    with ingest_span("ingest_message") as span:
        # Both per-source knobs in one PK get. `source_llm_enabled` is the
        # operator's switch for the whole LLM step; `allow_llm` narrows it by
        # the promo-thread veto, which is about THIS message rather than the
        # channel.
        source_llm_enabled, inherit_window = await _source_settings(session, source_id)
        allow_llm = source_llm_enabled and not await in_promo_thread(
            session, source_id, reply_to_message_id, matcher
        )
        parsed, decision_source, llm_attempted, llm_usage, llm_response = await _resolve(
            text, matcher, allow_llm=allow_llm
        )
        _apply_llm_to_raw(raw, llm_attempted, llm_usage, llm_response)

        # WHERE this message is about, resolved once: all three inference tiers
        # need it (each is region-gated, see domain.target_types) and so does
        # IngestContext below. It used to be computed twice, in the incident
        # tier and again for the context.
        region = await resolve_region(
            session, [h.district_id for h in parsed.districts], source_id
        )

        # Cross-message type inheritance: record this message's stated type, or
        # inherit a recent one from the same channel onto a bare-toponym sighting
        # ("Троя" mid-ballistic-attack -> missile, not unknown). Runs before every
        # branch below so a typed post updates the context even when it produces no
        # event of its own (e.g. a district-less "Балістика!"). The incident-level
        # fallback below is the second tier when the per-channel window has lapsed.
        inherited_inferred = _note_and_inherit_type(parsed, source_id, when, inherit_window,
                                                    region=region)
        type_from_incident = await _infer_incident_type(session, parsed, when, region)
        # Fourth tier — the LLM reads the type off the last two hours of the
        # whole feed. Last on purpose: it must never overrule a type the rules,
        # the channel or the live incident already established.
        type_from_llm = await _maybe_llm_type(session, raw, parsed, when, allow_llm=allow_llm,
                                              region=region,
                                              source_llm_enabled=source_llm_enabled,
                                              window_minutes=inherit_window)
        # …and its answer becomes this channel's context, so the next bare
        # toponym inherits it for free instead of re-asking (see
        # note_inferred_type for the measurement). The incident prior is
        # deliberately NOT recorded: it costs nothing to recompute and it is
        # already a whole-attack signal, so caching it per channel would only
        # let it outlive the incident that justified it.
        if type_from_llm is not None:
            note_inferred_type(source_id, type_from_llm, when)

        span.set_attribute("decision_source", decision_source)
        span.set_attribute("target_type", parsed.target_type)
        span.set_attribute("llm_attempted", llm_attempted)
        span.set_attribute("type_from_llm", type_from_llm or "")

        ctx = IngestContext(
            session=session, raw=raw, parsed=parsed, decision_source=decision_source,
            when=when, source_id=source_id, message_id=message_id,
            forwarded_from_id=forwarded_from_id,
            forwarded_from_channel_id=forwarded_from_channel_id,
            reply_to_message_id=reply_to_message_id,
            llm_summary=(llm_response.get("summary") or None
                         if llm_response is not None and decision_source == "llm" else None),
            type_inferred=(type_from_incident or type_from_llm is not None
                           or inherited_inferred),
            enforce_age=enforce_age,
            region=region,
            region_by_id=await district_regions(session),
        )
        span.set_attribute("region", ctx.region)

        triage_extra = await _maybe_triage(ctx, triage, matcher, allow_llm, source_llm_enabled)

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
        from ...models import District
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
        region=await resolve_region(session, [h.district_id for h in hits], job.source_id),
        region_by_id=await district_regions(session),
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
    from ..triage import TriageJob, route_verdict

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

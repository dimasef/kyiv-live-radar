"""Ingest pipeline entry points + orchestration. `ingest_message` is the
serialized live entry (shared by the Telethon listener and the simulator);
`process_parsed` is the reusable resolve->track->fuse half, also driven by
`scripts/reprocess_raw.py` and `process_rescued`."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from ...domain.incidents import find_active_incident, incident_type_prior
from ...models import RawMessage
from ...observability import ingest_span, metrics
from ...parsing import DistrictHit, DistrictMatcher, LlmUsage, ParseResult
from ..lock import ingest_lock
from ..results import Broadcast
from .context import IngestContext, _note_and_inherit_type
from .handlers import _dispatch, _handle_citywide, _handle_sighting, _ingest_outcome
from .resolve import _resolve, in_promo_thread


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


async def _infer_incident_type(session, parsed: ParseResult, when: datetime) -> bool:
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
    inc = await find_active_incident(session, when)
    prior = incident_type_prior(inc) if inc is not None else None
    if prior is not None:
        parsed.target_type = prior
        return True
    return False


async def _maybe_triage(ctx: IngestContext, triage: str, matcher: DistrictMatcher,
                        allow_llm: bool = True) -> list[Broadcast]:
    """Hand this message to the second-pass triage engine. 'live' enqueues a
    qualifying district-less/suppressed-but-threat-flavored message (reusing any
    inline LLM verdict — no second API call); 'replay' routes the STORED verdict
    inline for a deterministic reprocess. Marks the raw row so /raw shows where it
    went. Returns broadcasts from the replay path ([] for live/off).

    The triage imports are lazy: ingest and triage are mutually recursive (ingest
    enqueues to triage; triage's rescue calls back into process_rescued), so this
    direction stays in-function to keep the package importable without a cycle."""
    raw = ctx.raw
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
        allow_llm = not await in_promo_thread(session, source_id, reply_to_message_id, matcher)
        parsed, decision_source, llm_attempted, llm_usage, llm_response = await _resolve(
            text, matcher, allow_llm=allow_llm
        )
        _apply_llm_to_raw(raw, llm_attempted, llm_usage, llm_response)

        # Cross-message type inheritance: record this message's stated type, or
        # inherit a recent one from the same channel onto a bare-toponym sighting
        # ("Троя" mid-ballistic-attack -> missile, not unknown). Runs before every
        # branch below so a typed post updates the context even when it produces no
        # event of its own (e.g. a district-less "Балістика!"). The incident-level
        # fallback below is the second tier when the per-channel window has lapsed.
        _note_and_inherit_type(parsed, source_id, when)
        type_from_incident = await _infer_incident_type(session, parsed, when)

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
            enforce_age=enforce_age,
        )

        triage_extra = await _maybe_triage(ctx, triage, matcher, allow_llm)

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

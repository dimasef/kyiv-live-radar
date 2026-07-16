"""Async LLM triage engine — the second consumer of the LLM (see parsing/llm.py).

The rules parser answers synchronously and unchanged. Separately, a message that
is district-less / suppressed but still threat-flavored is enqueued here for an
async second pass that:
  * confirms a suppression (nothing surfaces), or
  * surfaces a directional / forecast / status context notice (+ a map axis for
    directional), or
  * (behind `triage_rescue_enabled`) RESCUES a wrongly-suppressed live threat,
    re-injecting it through the normal tracking handlers at its ORIGINAL
    timestamp.

Design constraints (see CLAUDE.md / the plan):
  * The API call never holds the ingest lock; all DB mutation re-acquires it.
  * A verdict already produced by the inline fallback is REUSED — never a second
    API call for the same message.
  * The LLM never declares clear/destroyed and never closes a track (rules + the
    official alert channel own відбій). Districts/origins are enum-railed.
  * One bounded in-process asyncio.Queue + one consumer task — no Redis/celery.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select

from ..config import settings
from ..db import SessionLocal
from ..domain.axes import AxisSignal, apply_axis_signal
from ..domain.origins import ORIGIN_BY_KEY, ORIGIN_KEYS, SECTORS
from ..feeds.common import build_matcher
from ..models import Notice, RawMessage, ThreatEvent, utcnow
from ..parsing.rules import ParseResult
from .results import Broadcast

log = logging.getLogger("triage")


@dataclass
class TriageJob:
    """One message queued for async triage. Carries everything a rescue needs to
    re-enter tracking at the message's original position."""

    raw_id: int
    text: str
    when: datetime
    source_id: int | None
    message_id: int | None
    reply_to_message_id: int | None
    forwarded_from_id: int | None
    forwarded_from_channel_id: int | None
    # The inline fallback's stored verdict, reused so a message that already paid
    # for an LLM call is never re-queried. None => the consumer calls llm_triage.
    verdict: dict | None


_queue: asyncio.Queue[TriageJob] | None = None


def get_queue() -> asyncio.Queue[TriageJob]:
    global _queue
    if _queue is None:
        _queue = asyncio.Queue(maxsize=settings.triage_queue_max)
    return _queue


def reset_queue() -> None:
    """Drop the queue (tests build a fresh event loop per case; a queue bound to
    a closed loop would raise)."""
    global _queue
    _queue = None


def should_triage(parsed: ParseResult, decision_source: str, llm_response: dict | None) -> bool:
    """Whether this message warrants an async triage pass. Enqueue only the
    classes that produced NO live event and are still worth a second look: a
    threat-flavored message the rules suppressed, or one the inline fallback
    couldn't localize. Never re-triage something that already became an event
    (districts / citywide / directional-axis / inline-LLM localization), a
    clear/destroyed, or pure junk."""
    if not settings.triage_enabled:
        return False
    if decision_source == "llm":       # inline fallback already localized it
        return False
    if parsed.directional:             # rules already raised an axis
        return False
    if parsed.districts or parsed.citywide:
        return False
    if parsed.status in ("clear", "destroyed"):
        return False
    if parsed.lost_signal or parsed.summary or parsed.target_pulse or parsed.promo:
        return False
    if llm_response is not None:       # inline call ran, didn't localize — reuse it
        return True
    suppressed = (parsed.aftermath or parsed.negated or parsed.civic_notice
                  or parsed.eppo_marks or parsed.siren_only
                  or parsed.political_quote or parsed.day_recap)
    threat_flavored = parsed.target_type != "unknown" or parsed.status in ("confirmed", "unconfirmed")
    return suppressed and threat_flavored


def enqueue_job(job: TriageJob) -> bool:
    """Non-blocking enqueue. Returns False when the queue is full (the caller
    marks the raw row triage_state='skipped') — a bounded drop under a barrage
    beats unbounded memory growth."""
    try:
        get_queue().put_nowait(job)
        return True
    except asyncio.QueueFull:
        log.warning("triage queue full (%d) — dropping raw %s", settings.triage_queue_max, job.raw_id)
        return False


# --- Cost guard -----------------------------------------------------------

_spend_cache: tuple[float, bool] | None = None  # (monotonic-ish epoch secs, ok)


async def llm_spend_ok() -> bool:
    """Whether LLM spend for the current UTC day AND month is under the caps
    (0 = unlimited). Cached ~60s so a barrage doesn't run a SUM per message.
    Gates both this engine and the inline fallback — graceful degrade to
    rules-only when the budget is exhausted."""
    global _spend_cache
    daily_cap = settings.llm_daily_budget_usd
    monthly_cap = settings.llm_monthly_budget_usd
    if daily_cap <= 0 and monthly_cap <= 0:
        return True
    now = utcnow()
    now_epoch = now.timestamp()
    if _spend_cache is not None and now_epoch - _spend_cache[0] < 60:
        return _spend_cache[1]
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    async with SessionLocal() as session:
        day_spend = await session.scalar(
            select(func.coalesce(func.sum(RawMessage.llm_cost_usd), 0.0))
            .where(RawMessage.event_time >= day_start)
        ) or 0.0
        month_spend = await session.scalar(
            select(func.coalesce(func.sum(RawMessage.llm_cost_usd), 0.0))
            .where(RawMessage.event_time >= month_start)
        ) or 0.0
    ok = (daily_cap <= 0 or day_spend < daily_cap) and (monthly_cap <= 0 or month_spend < monthly_cap)
    if not ok and (_spend_cache is None or _spend_cache[1]):
        log.warning("LLM budget reached (day=%.4f/%.2f month=%.4f/%.2f) — rules-only until it resets",
                    day_spend, daily_cap, month_spend, monthly_cap)
    _spend_cache = (now_epoch, ok)
    return ok


def _invalidate_spend_cache() -> None:
    global _spend_cache
    _spend_cache = None


# --- Consumer -------------------------------------------------------------

async def run_triage_consumer() -> None:
    """Lifespan task: drain the triage queue, one job at a time. Serial by
    design — the API call is the slow part and DB mutation must re-acquire the
    ingest lock anyway; parallelism would only contend on it."""
    queue = get_queue()
    while True:
        job = await queue.get()
        try:
            await _process_job(job)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("triage job failed (raw %s)", job.raw_id)
            await _mark_state(job.raw_id, "error")
        finally:
            queue.task_done()


async def _process_job(job: TriageJob) -> None:
    from .broadcast import broadcast_results  # lazy: avoids import cycle at startup

    verdict = job.verdict
    usage = None
    if verdict is None:
        if not await llm_spend_ok():
            await _mark_state(job.raw_id, "budget")
            return
        matcher = await build_matcher()
        from ..parsing.llm import llm_triage  # lazy: anthropic client
        verdict, usage = await llm_triage(job.text, matcher)
        _invalidate_spend_cache()

    # Every DB mutation happens under the ingest lock on a fresh session, so a
    # late verdict can never race a concurrently-arriving live message.
    from .ingest import _ingest_lock  # lazy: avoids import cycle
    async with _ingest_lock:
        async with SessionLocal() as session:
            raw = await session.get(RawMessage, job.raw_id)
            if raw is None:
                return
            if usage is not None:
                raw.llm_attempted = True
                raw.llm_input_tokens = usage.input_tokens
                raw.llm_output_tokens = usage.output_tokens
                raw.llm_cost_usd = usage.cost_usd
            if verdict is not None and raw.llm_response is None:
                raw.llm_response = verdict
            broadcasts, action, state = await route_verdict(session, raw, job, verdict)
            raw.triage_action = action
            raw.triage_state = state
            await session.commit()
            await broadcast_results(session, broadcasts)


async def _mark_state(raw_id: int, state: str) -> None:
    async with SessionLocal() as session:
        raw = await session.get(RawMessage, raw_id)
        if raw is not None:
            raw.triage_state = state
            await session.commit()


def _age_minutes(when: datetime, now: datetime) -> float:
    wn = when.replace(tzinfo=None) if when.tzinfo is not None else when
    nn = now.replace(tzinfo=None) if now.tzinfo is not None else now
    return (nn - wn).total_seconds() / 60.0


# --- Routing table --------------------------------------------------------

async def route_verdict(
    session, raw: RawMessage, job: TriageJob, verdict: dict | None, enforce_age: bool = True
) -> tuple[list[Broadcast], str, str]:
    """Map a verdict to (broadcasts, triage_action, triage_state). Applies the
    code-side guardrails on top of the LLM's category (D4): districts/origins
    enum-only (already enforced in llm._normalize), clear/destroyed never
    actionable, axes only via the fusion-gated axis engine.

    `enforce_age=False` for the deterministic reprocess replay (ingest.py), where
    each stored verdict is re-applied at its own chronological position and "age
    since now" is meaningless."""
    if verdict is None:
        return [], "none", "error"
    # A verdict that lands long after the message is audit-only — the live
    # picture has moved on; recording it still tunes the corpus.
    if enforce_age and _age_minutes(job.when, utcnow()) > settings.triage_max_age_minutes:
        return [], "late", "done"

    category = verdict.get("category", "noise")
    if not verdict.get("surface") or category == "noise":
        return [], "suppress_confirmed", "done"
    if category == "directional":
        return await _route_directional(session, raw, job, verdict)
    if category in ("forecast", "status"):
        notice = await _make_triage_notice(session, category, verdict, job, origin_key=None)
        return [Broadcast("notice", notice=notice)], "notice", "done"
    if category in ("localized", "citywide"):
        return await _route_rescue(session, raw, job, verdict, enforce_age=enforce_age)
    return [], "suppress_confirmed", "done"


def _sector_for(verdict: dict) -> tuple[str | None, str | None]:
    """(origin_key, sector) a directional verdict points along, or (None, None)
    when it names neither a curated origin nor an explicit compass sector — then
    it can only be a notice, not a placed wedge."""
    origin_key = verdict.get("origin_place")
    if origin_key in ORIGIN_KEYS:
        return origin_key, ORIGIN_BY_KEY[origin_key].sector
    sector = verdict.get("origin_sector")
    if sector in SECTORS:
        return None, sector
    return None, None


def _source_dedup_key(job: TriageJob) -> str:
    """Independent-source identity for axis corroboration — a repost is
    attributed to its origin channel, mirroring fusion._origin_keys' intent, so
    one channel reposting itself doesn't inflate an axis' corroboration."""
    if job.forwarded_from_channel_id is not None:
        return f"orig:{job.forwarded_from_channel_id}"
    return f"src:{job.source_id}"


async def _route_directional(
    session, raw: RawMessage, job: TriageJob, verdict: dict
) -> tuple[list[Broadcast], str, str]:
    origin_key, sector = _sector_for(verdict)
    notice = await _make_triage_notice(session, "directional", verdict, job, origin_key=origin_key)
    broadcasts: list[Broadcast] = [Broadcast("notice", notice=notice)]
    if sector is not None:
        axis = await apply_axis_signal(session, AxisSignal(
            sector=sector,
            target_type=verdict.get("target_type", "unknown"),
            when=job.when,
            origin_key=origin_key,
            source_dedup_key=_source_dedup_key(job),
            raw_id=raw.id,
        ))
        if axis is not None:
            broadcasts.append(Broadcast("axis", axis=axis))
        return broadcasts, "axis", "done"
    return broadcasts, "notice", "done"


async def _make_triage_notice(
    session, kind: str, verdict: dict, job: TriageJob, origin_key: str | None
) -> Notice:
    text = verdict.get("summary") or job.text
    notice = Notice(
        kind=kind,
        text=text,
        target_type=verdict.get("target_type", "unknown"),
        source_id=job.source_id,
        event_time=job.when,
        source_message_id=job.message_id,
        origin=origin_key,
        generated_by="llm",
    )
    session.add(notice)
    await session.commit()
    return notice


# --- Rescue (behind triage_rescue_enabled) --------------------------------

async def _route_rescue(
    session, raw: RawMessage, job: TriageJob, verdict: dict, enforce_age: bool = True
) -> tuple[list[Broadcast], str, str]:
    """Re-inject a wrongly-suppressed live threat through the normal tracking
    handlers. The riskiest path (a false rescue = a phantom track): every gate
    is code-side, and it ships disabled — until enabled, a candidate is only
    recorded for /raw audit."""
    # Never rescue an LLM-declared clear/destroyed — rules + the official alert
    # channel own those (guardrail D4).
    if verdict.get("status") in ("clear", "destroyed"):
        return [], "rescue_candidate", "done"
    has_localization = bool(verdict.get("district_ids")) or verdict.get("category") == "citywide"
    if not has_localization:
        return [], "rescue_candidate", "done"
    if not settings.triage_rescue_enabled:
        # Dark-launch: observe rescue_candidate on /raw before enabling.
        return [], "rescue_candidate", "done"
    if verdict.get("confidence", 0.0) < settings.triage_rescue_min_confidence:
        return [], "rescue_candidate", "done"

    max_age = min(settings.triage_rescue_max_age_minutes, settings.track_stale_minutes)
    if enforce_age and _age_minutes(job.when, utcnow()) > max_age:
        # A track born past the stale window would be closed on the sweeper's
        # next tick — pointless. Record it, don't act.
        return [], "late", "done"

    # Idempotency: never double-produce. If this raw already yielded any event
    # (a live message landed first), the rescue is a no-op.
    existing = await session.scalar(
        select(func.count()).select_from(ThreatEvent).where(
            ThreatEvent.source_id == job.source_id,
            ThreatEvent.source_message_id == job.message_id,
        )
    )
    if job.message_id is not None and existing:
        return [], "rescued", "done"

    from .ingest import process_rescued  # lazy: avoids import cycle
    broadcasts = await process_rescued(session, raw=raw, job=job, verdict=verdict)
    return broadcasts, "rescued", "done"

"""Per-source quality signals for the /admin channel-management console.

Everything here is derived on-demand (a handful of GROUP BY source_id queries)
from tables that already carry a source_id — raw_messages, threat_events (joined
to threats for the conflict flag) and parser_corrections (joined via
raw_message_id). No per-source rollup is stored; for a single-user MVP recomputing
on tab open is simpler and always fresh.

The `quality_score` is INFORMATIONAL only — it does not feed fusion.py (Source.
trust_weight stays inert by design). It's a 0..100 blend of the component rates,
renormalized over whichever components have a denominator so a brand-new channel
with no events yet doesn't score 0 for lack of data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ParserCorrection, RawMessage, Source, Threat, ThreatEvent, utcnow
from ..timeutil import naive

# Quality-score component weights (must sum to 1.0). Tuned by feel, not data —
# easy to recalibrate here. Each component is a 0..1 "goodness" (higher better).
_W_COVERAGE = 0.35  # share of the channel's messages we could place on the map
_W_LOW_CORRECTION = 0.35  # admin rarely had to fix this channel's parses
_W_LOW_CONFLICT = 0.15  # its reports rarely disagreed with the fused type
_W_LOW_LLM = 0.15  # low reliance on the LLM fallback


@dataclass
class SourceStats:
    messages_total: int = 0
    messages_processed: int = 0
    events_produced: int = 0
    llm_fallback_rate: float | None = None
    # Share of this channel's messages that got localized onto the map (a
    # threat_event). None for alert-role channels, which don't produce events.
    coverage_rate: float | None = None
    correction_rate: float | None = None
    conflict_share: float | None = None
    quality_score: float | None = None
    last_message_at: datetime | None = None


def _ratio(numerator: int, denominator: int) -> float | None:
    return (numerator / denominator) if denominator else None


def _quality_score(s: SourceStats) -> float | None:
    """Weighted blend of the goodness components, renormalized over the ones that
    have a denominator (None components are dropped, not treated as 0)."""
    parts: list[tuple[float, float]] = []  # (weight, goodness 0..1)
    if s.coverage_rate is not None:
        parts.append((_W_COVERAGE, s.coverage_rate))
    if s.correction_rate is not None:
        parts.append((_W_LOW_CORRECTION, 1.0 - s.correction_rate))
    if s.conflict_share is not None:
        parts.append((_W_LOW_CONFLICT, 1.0 - s.conflict_share))
    if s.llm_fallback_rate is not None:
        parts.append((_W_LOW_LLM, 1.0 - s.llm_fallback_rate))
    total_w = sum(w for w, _ in parts)
    if not total_w:
        return None
    blended = sum(w * g for w, g in parts) / total_w
    return round(100.0 * max(0.0, min(1.0, blended)), 1)


async def compute_source_stats(
    session: AsyncSession, window_days: int = 30
) -> dict[int, SourceStats]:
    """Per-source quality metrics over the last `window_days`, keyed by source_id."""
    cutoff = naive(utcnow() - timedelta(days=window_days))
    stats: dict[int, SourceStats] = {}

    def _get(sid: int) -> SourceStats:
        return stats.setdefault(sid, SourceStats())

    # --- raw_messages: volume, processed, LLM-fallback rate ---
    # func.count over a nullable column counts only non-NULL, so llm_known is the
    # denominator that excludes pre-column history (llm_attempted IS NULL).
    llm_true = func.sum(case((RawMessage.llm_attempted.is_(True), 1), else_=0))
    llm_known = func.count(RawMessage.llm_attempted)
    raw_rows = await session.execute(
        select(
            RawMessage.source_id,
            func.count(RawMessage.id),
            func.sum(case((RawMessage.processed.is_(True), 1), else_=0)),
            llm_true,
            llm_known,
        )
        .where(RawMessage.source_id.is_not(None), RawMessage.event_time >= cutoff)
        .group_by(RawMessage.source_id)
    )
    for sid, total, processed, l_true, l_known in raw_rows:
        s = _get(sid)
        s.messages_total = total or 0
        s.messages_processed = int(processed or 0)
        s.llm_fallback_rate = _ratio(int(l_true or 0), int(l_known or 0))

    # --- threat_events (joined to threats): productivity + conflict share ---
    conflict_ev = func.sum(case((Threat.has_conflict.is_(True), 1), else_=0))
    ev_rows = await session.execute(
        select(
            ThreatEvent.source_id,
            func.count(ThreatEvent.id),
            conflict_ev,
        )
        .join(Threat, ThreatEvent.threat_id == Threat.id)
        .where(ThreatEvent.source_id.is_not(None), ThreatEvent.event_time >= cutoff)
        .group_by(ThreatEvent.source_id)
    )
    for sid, total, conflicts in ev_rows:
        s = _get(sid)
        s.events_produced = total or 0
        s.conflict_share = _ratio(int(conflicts or 0), total or 0)

    # --- coverage: share of the channel's messages we could place on the map.
    # A message is "localized" if it produced a threat_event (matched by
    # source + message id). Denominator is ALL the channel's messages, so a
    # channel that mostly posts news/flood reads lower than a focused spotter. ---
    loc_rows = await session.execute(
        select(RawMessage.source_id, func.count(func.distinct(RawMessage.id)))
        .join(
            ThreatEvent,
            (ThreatEvent.source_id == RawMessage.source_id)
            & (ThreatEvent.source_message_id == RawMessage.message_id),
        )
        .where(RawMessage.source_id.is_not(None), RawMessage.event_time >= cutoff)
        .group_by(RawMessage.source_id)
    )
    localized = {sid: int(n or 0) for sid, n in loc_rows}
    # Alert-role channels feed the air-raid alert parser, not the map — "coverage"
    # is meaningless for them, so leave it None rather than a misleading 0%.
    alert_ids = set(await session.scalars(select(Source.id).where(Source.role == "alert")))
    for sid, s in stats.items():
        if sid not in alert_ids:
            s.coverage_rate = _ratio(localized.get(sid, 0), s.messages_total)

    # --- parser_corrections: how often the parser was WRONG on this channel ---
    corr_rows = await session.execute(
        select(RawMessage.source_id, func.count(ParserCorrection.id))
        .join(ParserCorrection, ParserCorrection.raw_message_id == RawMessage.id)
        .where(RawMessage.source_id.is_not(None), RawMessage.event_time >= cutoff)
        .group_by(RawMessage.source_id)
    )
    for sid, corrections in corr_rows:
        s = _get(sid)
        s.correction_rate = _ratio(int(corrections or 0), s.messages_processed)

    # --- last seen (all-time, not windowed): is this channel still alive? ---
    last_rows = await session.execute(
        select(RawMessage.source_id, func.max(RawMessage.event_time))
        .where(RawMessage.source_id.is_not(None))
        .group_by(RawMessage.source_id)
    )
    for sid, last_at in last_rows:
        _get(sid).last_message_at = last_at

    for s in stats.values():
        s.quality_score = _quality_score(s)
    return stats

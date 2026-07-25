"""Coverage-gap detection for the admin console.

A "gap" is a message the current parser thinks IS a localizable aerial threat
(`pipeline.ingest.should_fallback` is True — the exact gate that routes to the
LLM) yet which produced NO sighting and NO notice: i.e. neither the rules, the
LLM, nor triage could pin it to a district. That's almost always a missing
gazetteer entry — the primary accuracy lever (see CLAUDE.md / WORKFLOW.md).

Kept out of routes.py so the scan logic is unit-testable on its own.
"""

from __future__ import annotations

from sqlalchemy import select

from ..models import Notice, RawMessage, Source, ThreatEvent
from ..parsing import DistrictMatcher, parse_message
from ..pipeline.ingest import should_fallback


async def find_coverage_gaps(
    session, matcher: DistrictMatcher, *, limit: int = 50, scan: int = 800
) -> list[dict]:
    """Scan the most recent `scan` raw messages, return up to `limit` gaps
    (newest first). Bounded window keeps it cheap for the single-user MVP."""
    raws = list(
        await session.scalars(select(RawMessage).order_by(RawMessage.id.desc()).limit(scan))
    )
    # Messages that already became a sighting or a notice are handled — exclude
    # them. Keyed by (source_id, message_id), the raw↔event/notice link.
    localized = {
        (r.source_id, r.source_message_id)
        for r in (
            await session.execute(
                select(ThreatEvent.source_id, ThreatEvent.source_message_id).where(
                    ThreatEvent.source_message_id.is_not(None)
                )
            )
        ).all()
    }
    noticed = {
        (r.source_id, r.source_message_id)
        for r in (
            await session.execute(
                select(Notice.source_id, Notice.source_message_id).where(
                    Notice.source_message_id.is_not(None)
                )
            )
        ).all()
    }
    source_names = {s.id: s.name for s in await session.scalars(select(Source))}

    gaps: list[dict] = []
    for raw in raws:
        if (raw.source_id, raw.message_id) in localized:
            continue
        if (raw.source_id, raw.message_id) in noticed:
            continue
        parsed = parse_message(raw.text, matcher)
        if parsed.districts or not should_fallback(parsed):
            continue
        gaps.append(
            {
                "raw_message_id": raw.id,
                "text": raw.text,
                "event_time": raw.event_time,
                "source_name": source_names.get(raw.source_id),
                "detected_target_type": parsed.target_type,
                "detected_status": parsed.status,
            }
        )
        if len(gaps) >= limit:
            break
    return gaps

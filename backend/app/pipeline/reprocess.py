"""Rebuild every threat / incident from stored `raw_messages` through the
CURRENT parser/gazetteer/tracking pipeline (e.g. after a parser change).

Destructive to threats/threat_events/incidents; `raw_messages` are preserved.
Shared by `scripts/reprocess_raw.py` (CLI) and, gated by REPROCESS_ON_BOOT, by
app startup — running at boot BEFORE the live listener starts makes a one-off
prod reprocess race-free (nothing ingests concurrently) and needs no external
DB access (it runs inside the service, on the internal DB).
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from ..config import settings
from ..db import SessionLocal
from ..feeds.common import RegionMatchers
from ..gazetteer import DISTRICTS
from ..migrate import upgrade_to_head
from ..models import (
    Alert,
    District,
    Incident,
    Notice,
    PushSubscription,
    RawMessage,
    Source,
    Threat,
    ThreatAxis,
    ThreatEvent,
)
from ..seed import seed_districts
from ..timeutil import naive
from .ingest import process_parsed, process_parsed_alert

log = logging.getLogger("reprocess")


async def _drop_stale_districts() -> None:
    current = {d["name_en"] for d in DISTRICTS}
    async with SessionLocal() as s:
        stale = [d for d in await s.scalars(select(District)) if d.name_en not in current]
        for d in stale:
            await s.delete(d)
        if stale:
            await s.commit()


async def _wipe_tracks() -> None:
    # Notices/alerts are re-emitted by the ingest replay below, so they must
    # be wiped too — otherwise every reprocess DUPLICATES all all-clear/
    # summary notices and alert windows, and a wrong one created by older
    # code survives forever since the current parser never recreates it.
    async with SessionLocal() as s:
        await s.execute(delete(ThreatEvent))
        await s.execute(delete(Threat))
        await s.execute(delete(Incident))
        await s.execute(delete(Notice))
        await s.execute(delete(Alert))
        await s.execute(delete(ThreatAxis))
        # Rebuilt tracks reuse ids from 1 — per-track push bookkeeping keyed by
        # the OLD ids would wrongly suppress pushes for unrelated new tracks.
        for sub in await s.scalars(select(PushSubscription)):
            sub.danger_state = {}
        await s.commit()


async def scope_cutoff(s, last: int) -> datetime | None:
    """The instant a "last N messages" replay must start from.

    Naively that is the oldest of the last `last` raw messages — but a track,
    an alert or an incident that STARTED before that point and continued past it
    would be cut in half: its early events survive the wipe while its later ones
    are rebuilt, leaving one target as two. So the cutoff snaps back to the start
    of anything it lands inside, and keeps snapping until it lands in a gap.
    A partial rebuild therefore replays at least N messages, sometimes a few
    more — never fewer.

    Returns None when there is nothing stored (nothing to rebuild).
    """
    times = list(
        await s.scalars(
            select(RawMessage.event_time).order_by(RawMessage.event_time.desc()).limit(last)
        )
    )
    if not times:
        return None
    cutoff = min(naive(t) for t in times)

    spans: list[tuple[datetime, datetime]] = []
    for t in await s.scalars(select(Threat).options(selectinload(Threat.events))):
        stamps = [naive(e.event_time) for e in t.events]
        if stamps:
            spans.append((min(stamps), max(stamps)))
    for a in await s.scalars(select(Alert)):
        # An open alert (ended_at NULL) runs to now, so it spans any cutoff
        # after its start.
        end = naive(a.ended_at) if a.ended_at is not None else datetime.max
        spans.append((naive(a.started_at), end))
    for inc in await s.scalars(select(Incident)):
        end = naive(inc.ended_at) if inc.ended_at is not None else datetime.max
        spans.append((naive(inc.started_at), end))

    # Each pass can only move the cutoff earlier, and only onto the start of an
    # existing span, so it terminates; the bound is belt-and-braces.
    for _ in range(len(spans) + 1):
        moved = min((start for start, end in spans if start < cutoff <= end), default=cutoff)
        if moved == cutoff:
            break
        cutoff = moved
    return cutoff


async def _wipe_since(cutoff: datetime) -> None:
    """Delete everything the replay from `cutoff` will rebuild, and nothing else.

    Thanks to `scope_cutoff`'s snapping, no surviving track/alert/incident
    reaches past the cutoff — so this is a clean truncation, not a partial
    dismantling of live objects."""
    async with SessionLocal() as s:
        doomed: list[Threat] = []
        for t in await s.scalars(select(Threat).options(selectinload(Threat.events))):
            if any(naive(e.event_time) >= cutoff for e in t.events):
                doomed.append(t)
        doomed_ids = {t.id for t in doomed}
        for t in doomed:
            for e in t.events:
                await s.delete(e)
            await s.delete(t)
        await s.flush()

        for inc in await s.scalars(select(Incident).options(selectinload(Incident.threats))):
            if all(t.id in doomed_ids for t in inc.threats):
                await s.delete(inc)
        for n in await s.scalars(select(Notice)):
            if naive(n.event_time) >= cutoff:
                await s.delete(n)
        for a in await s.scalars(select(Alert)):
            if naive(a.started_at) >= cutoff:
                await s.delete(a)
        for ax in await s.scalars(select(ThreatAxis)):
            if naive(ax.created_at) >= cutoff:
                await s.delete(ax)

        # Rebuilt tracks can reuse a freed id (SQLite hands back max+1), and
        # per-track push bookkeeping under an old id would then suppress pushes
        # for an unrelated new track.
        if doomed_ids:
            for sub in await s.scalars(select(PushSubscription)):
                kept = {k: v for k, v in (sub.danger_state or {}).items() if int(k) not in doomed_ids}
                if len(kept) != len(sub.danger_state or {}):
                    sub.danger_state = kept
        await s.commit()


async def run_reprocess(
    no_llm: bool = True, limit: int | None = None, last: int | None = None
) -> dict:
    """Wipe and rebuild tracks/incidents from raw_messages. Returns counts.

    `no_llm` disables the LLM fallback for the run only — the original setting is
    restored afterwards so the live listener keeps its configured behavior.

    `last` rebuilds only the tail: the last N stored messages (widened by
    `scope_cutoff` so nothing is cut in half), leaving older history untouched.
    That is the everyday shape of this tool — after a parser fix, what matters is
    the stretch still on the map. Without it the whole history is rebuilt.

    `limit` is the CLI's "just the first N messages" smoke-test switch; it does
    NOT scope the wipe."""
    original_llm = settings.llm_fallback_enabled
    if no_llm:
        settings.llm_fallback_enabled = False
    try:
        # Ensure the schema is current before we replay — idempotent, and it lets
        # the standalone CLI pick up any migrations (e.g. a new column) that the
        # server's lifespan would otherwise have applied at startup, so a CLI
        # reprocess can't fail on them.
        await upgrade_to_head()
        await _drop_stale_districts()
        await seed_districts()

        cutoff: datetime | None = None
        if last:
            async with SessionLocal() as s:
                cutoff = await scope_cutoff(s, last)
        if cutoff is None:
            await _wipe_tracks()
        else:
            await _wipe_since(cutoff)

        async with SessionLocal() as s:
            districts = list(await s.scalars(select(District)))
            sources = list(await s.scalars(select(Source)))
            stmt = select(RawMessage).order_by(RawMessage.event_time)
            if cutoff is not None:
                stmt = stmt.where(RawMessage.event_time >= cutoff)
            raws = list(await s.scalars(stmt))
        # Per-region matchers, picked by each message's own channel — the
        # rebuild must resolve homonyms exactly as the live listener did.
        matchers = RegionMatchers(districts)
        role_by_source_id = {src.id: src.role for src in sources}
        region_by_source_id = {src.id: src.region for src in sources}
        if limit:
            raws = raws[:limit]

        log.info("reprocess: replaying %d raw messages", len(raws))
        matched = 0
        for i, raw in enumerate(raws, 1):
            text = (raw.text or "").strip()
            if not text:
                continue
            role = role_by_source_id.get(raw.source_id, "spotter")
            async with SessionLocal() as s:
                r = await s.get(RawMessage, raw.id)
                if role == "alert":
                    broadcasts = await process_parsed_alert(
                        s, raw=r, text=text, when=raw.event_time, source_id=raw.source_id,
                    )
                else:
                    broadcasts = await process_parsed(
                        s, raw=r, text=text,
                        matcher=matchers.for_region(region_by_source_id.get(raw.source_id)),
                        when=raw.event_time,
                        source_id=raw.source_id, message_id=raw.message_id,
                        forwarded_from_id=raw.forwarded_from_id,
                        forwarded_from_channel_id=raw.forwarded_from_channel_id,
                        reply_to_message_id=raw.reply_to_message_id,
                        # Replay stored LLM triage verdicts deterministically (no
                        # API, no queue) so a reprocess rebuilds axes/notices/
                        # rescues exactly, at each message's own position.
                        triage="replay",
                    )
                if broadcasts:
                    matched += 1
            if i % 100 == 0:
                log.info("reprocess %d/%d...", i, len(raws))

        async with SessionLocal() as s:
            n_threats = len(list(await s.scalars(select(Threat))))
            n_events = len(list(await s.scalars(select(ThreatEvent))))
        result = {"messages": len(raws), "matched": matched,
                  "tracks": n_threats, "events": n_events,
                  "from": cutoff.isoformat() if cutoff else None}
        log.info("reprocess done: %s", result)
        return result
    finally:
        settings.llm_fallback_enabled = original_llm

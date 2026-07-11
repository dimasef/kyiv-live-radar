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

from sqlalchemy import delete, select

from .config import settings
from .db import SessionLocal
from .gazetteer import DISTRICTS
from .ingest import _process_parsed
from .models import District, Incident, Notice, RawMessage, Threat, ThreatEvent
from .parser import DistrictMatcher
from .seed import seed_districts

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
    # Notices are re-emitted by the ingest replay below, so they must be wiped
    # too — otherwise every reprocess DUPLICATES all all-clear/summary notices,
    # and a wrong notice created by older code (e.g. a news post mis-read as a
    # "відбій") survives forever since the current parser never recreates it.
    async with SessionLocal() as s:
        await s.execute(delete(ThreatEvent))
        await s.execute(delete(Threat))
        await s.execute(delete(Incident))
        await s.execute(delete(Notice))
        await s.commit()


async def run_reprocess(no_llm: bool = True, limit: int | None = None) -> dict:
    """Wipe and rebuild all tracks/incidents from raw_messages. Returns counts.

    `no_llm` disables the LLM fallback for the run only — the original setting is
    restored afterwards so the live listener keeps its configured behavior."""
    original_llm = settings.llm_fallback_enabled
    if no_llm:
        settings.llm_fallback_enabled = False
    try:
        await _drop_stale_districts()
        await seed_districts()
        await _wipe_tracks()

        async with SessionLocal() as s:
            districts = list(await s.scalars(select(District)))
            raws = list(await s.scalars(select(RawMessage).order_by(RawMessage.event_time)))
        matcher = DistrictMatcher(districts)
        if limit:
            raws = raws[:limit]

        log.info("reprocess: replaying %d raw messages", len(raws))
        matched = 0
        for i, raw in enumerate(raws, 1):
            text = (raw.text or "").strip()
            if not text:
                continue
            async with SessionLocal() as s:
                r = await s.get(RawMessage, raw.id)
                broadcasts = await _process_parsed(
                    s, raw=r, text=text, matcher=matcher, when=raw.event_time,
                    source_id=raw.source_id, message_id=raw.message_id,
                    forwarded_from_id=raw.forwarded_from_id,
                    reply_to_message_id=raw.reply_to_message_id,
                )
                if broadcasts:
                    matched += 1
            if i % 100 == 0:
                log.info("reprocess %d/%d...", i, len(raws))

        async with SessionLocal() as s:
            n_threats = len(list(await s.scalars(select(Threat))))
            n_events = len(list(await s.scalars(select(ThreatEvent))))
        result = {"messages": len(raws), "matched": matched,
                  "tracks": n_threats, "events": n_events}
        log.info("reprocess done: %s", result)
        return result
    finally:
        settings.llm_fallback_enabled = original_llm

"""One-off: rebuild ALL tracks from the existing raw_messages using the CURRENT
parser + gazetteer + tracking logic — lets historical data benefit from parser/
gazetteer improvements made after it was first ingested (new localities, fixed
keyword lists, negation handling, etc.) without re-fetching Telegram history.

Wipes threat_events + threats (raw_messages/sources untouched) and replays
every raw message, in true chronological order across all channels, through
the same `ingest._process_parsed` pipeline live ingestion uses (parser -> LLM
fallback -> tracking -> fusion) — `_process_parsed` skips the "insert a new
raw_message" step so it isn't blocked by the ingest-level dedup guard.

Also drops any District row no longer present in app.gazetteer.DISTRICTS —
seed_districts() only ever ADDS, so a gazetteer entry removed in code (e.g.
"Українка", dropped for colliding with the Russian Ukrainka airbase name)
would otherwise linger in the live table forever and keep matching.

Run with the backend STOPPED — this wipes/rebuilds shared tables and races
with any concurrently-running live ingestion (the asyncio.Lock in ingest.py
only serializes within one process, not across this script + a running
uvicorn).

    cd backend && .venv/bin/python scripts/reprocess_raw.py [--no-llm] [--limit N]

--no-llm  skip the Claude Haiku fallback (rule-only, free, fast — good for a
          dry run before spending on the full pass).
--limit N only reprocess the N oldest raw_messages (for a quick smoke test).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.gazetteer import DISTRICTS  # noqa: E402
from app.ingest import _process_parsed  # noqa: E402
from app.models import District, RawMessage, Threat, ThreatEvent  # noqa: E402
from app.parser import DistrictMatcher  # noqa: E402


async def _drop_stale_districts() -> None:
    current_names = {d["name_en"] for d in DISTRICTS}
    async with SessionLocal() as s:
        stale = [d for d in await s.scalars(select(District)) if d.name_en not in current_names]
        for d in stale:
            print(f"  dropping stale district: {d.name_uk} ({d.name_en})")
            await s.delete(d)
        if stale:
            await s.commit()


async def _wipe_tracks() -> None:
    async with SessionLocal() as s:
        await s.execute(delete(ThreatEvent))
        await s.execute(delete(Threat))
        await s.commit()


async def main() -> None:
    no_llm = "--no-llm" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    if no_llm:
        settings.llm_fallback_enabled = False
        print("LLM fallback disabled for this run (--no-llm)")

    print("dropping stale gazetteer districts...")
    await _drop_stale_districts()

    print("wiping threats + threat_events (raw_messages untouched)...")
    await _wipe_tracks()

    async with SessionLocal() as s:
        districts = list(await s.scalars(select(District)))
        raws = list(await s.scalars(select(RawMessage).order_by(RawMessage.event_time)))
    matcher = DistrictMatcher(districts)
    if limit:
        raws = raws[:limit]

    print(f"replaying {len(raws)} raw messages through the current pipeline...")
    matched = 0
    for i, raw in enumerate(raws, 1):
        text = (raw.text or "").strip()
        if not text:
            continue
        async with SessionLocal() as s:
            r = await s.get(RawMessage, raw.id)
            broadcasts = await _process_parsed(
                s,
                raw=r,
                text=text,
                matcher=matcher,
                when=raw.event_time,
                source_id=raw.source_id,
                message_id=raw.message_id,
                forwarded_from_id=raw.forwarded_from_id,
                reply_to_message_id=raw.reply_to_message_id,
            )
            if broadcasts:
                matched += 1
        if i % 50 == 0:
            print(f"  {i}/{len(raws)}...")

    async with SessionLocal() as s:
        threats = list(await s.scalars(select(Threat)))
        events = list(await s.scalars(select(ThreatEvent)))

    print(f"\ndone: {len(raws)} messages replayed, {matched} produced events")
    print(f"tracks rebuilt: {len(threats)}, events rebuilt: {len(events)}")


if __name__ == "__main__":
    asyncio.run(main())

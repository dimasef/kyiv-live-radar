"""One-off: rebuild ALL tracks from the existing raw_messages using the CURRENT
parser + gazetteer + tracking logic — lets historical data benefit from parser/
gazetteer improvements made after it was first ingested, without re-fetching
Telegram history.

Thin CLI wrapper over app.pipeline.reprocess.run_reprocess (the same code the
server runs at boot when REPROCESS_ON_BOOT is set). Wipes threat_events/
threats/incidents (raw_messages/sources untouched) and replays every raw
message in chronological order through pipeline.ingest.process_parsed.

Run with the backend STOPPED — it wipes/rebuilds shared tables and races any
concurrently-running live ingestion (the asyncio.Lock in ingest only serializes
within one process). On prod, prefer REPROCESS_ON_BOOT (race-free) instead.

    cd backend && .venv/bin/python scripts/reprocess_raw.py [--no-llm] [--limit N]
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pipeline.reprocess import run_reprocess  # noqa: E402


async def main() -> None:
    no_llm = "--no-llm" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    if no_llm:
        print("LLM fallback disabled for this run (--no-llm)")
    print("reprocessing (wipe + replay through current pipeline)...")
    result = await run_reprocess(no_llm=no_llm, limit=limit)
    print(
        f"\ndone: {result['messages']} messages replayed, {result['matched']} produced events\n"
        f"tracks rebuilt: {result['tracks']}, events rebuilt: {result['events']}"
    )


if __name__ == "__main__":
    asyncio.run(main())

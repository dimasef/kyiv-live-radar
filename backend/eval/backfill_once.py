"""One-shot: wipe the tracking tables, backfill recent history across all
configured channels through the REAL ingest pipeline, then exit. Use before
eval/analyze.py to get a clean accuracy picture (not stacked on prior runs).

Stop the live listener first (shares the Telegram session). Reads only.

    cd backend && TELEGRAM_BACKFILL=100 .venv/bin/python eval/backfill_once.py
    cd backend && .venv/bin/python eval/analyze.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.models import District, RawMessage, Threat, ThreatEvent  # noqa: E402
from app.parser import DistrictMatcher  # noqa: E402
from app.seed import seed_districts, seed_sources  # noqa: E402
from app.telegram_listener import (  # noqa: E402
    _backfill,
    _ensure_sources,
    _resolve_channel,
)


async def _reset() -> None:
    async with SessionLocal() as s:
        # threat_events cascades from threats, but clear explicitly to be safe.
        await s.execute(delete(ThreatEvent))
        await s.execute(delete(Threat))
        await s.execute(delete(RawMessage))
        await s.commit()


async def main() -> None:
    from telethon import TelegramClient

    await init_db()
    await seed_districts()
    await seed_sources()
    await _reset()

    client = TelegramClient(settings.telegram_session, settings.telegram_api_id,
                            settings.telegram_api_hash)
    await client.start()

    entities = []
    for raw in settings.telegram_channel_list:
        try:
            entities.append(await _resolve_channel(client, raw))
        except Exception as ex:
            print(f"skip {raw}: {ex}", file=sys.stderr)
    if not entities:
        print("no channels resolved", file=sys.stderr)
        await client.disconnect()
        return

    id_to_source = await _ensure_sources(entities)
    async with SessionLocal() as s:
        districts = list(await s.scalars(select(District)))
    matcher = DistrictMatcher(districts)

    await _backfill(client, entities, id_to_source, matcher)
    await client.disconnect()
    print(f"backfill done: {settings.telegram_backfill}/channel across "
          f"{len(entities)} channels")


if __name__ == "__main__":
    asyncio.run(main())

"""One-off: remove duplicate raw_messages/threat_events created by repeated
Telegram backfills before the ingest-level dedup guard existed (see
ingest._ingest_locked's upfront (source_id, message_id) check — every restart
with TELEGRAM_BACKFILL>0 used to blindly re-ingest the same recent messages as
brand-new rows). Keeps the EARLIEST row per duplicate group, recomputes fusion
for affected tracks, and deletes any track left with zero events. Idempotent —
safe to re-run (no-op once the data is clean).

    cd backend && .venv/bin/python scripts/dedupe_ingest.py
"""

from __future__ import annotations

import asyncio
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import RawMessage, Threat, ThreatEvent  # noqa: E402
from app.tracking import apply_fusion  # noqa: E402


async def main() -> None:
    async with SessionLocal() as s:
        # --- 1. Dedupe raw_messages by (source_id, message_id) ---
        raws = list(await s.scalars(select(RawMessage)))
        raw_groups: dict[tuple, list[RawMessage]] = defaultdict(list)
        for r in raws:
            if r.message_id is not None:
                raw_groups[(r.source_id, r.message_id)].append(r)

        raw_deleted = 0
        for rows in raw_groups.values():
            if len(rows) <= 1:
                continue
            rows.sort(key=lambda r: r.id)
            for extra in rows[1:]:
                await s.delete(extra)
                raw_deleted += 1
        await s.commit()

        # --- 2. Dedupe threat_events by (source_id, source_message_id, district_id)
        #     — this key is safe because DistrictMatcher.find() already dedupes
        #     districts WITHIN one message (dict keyed by district id), so a
        #     genuine single ingest never produces two events with this same key;
        #     any group of size >1 here is purely from repeat backfill re-ingestion. ---
        events = list(await s.scalars(select(ThreatEvent)))
        event_groups: dict[tuple, list[ThreatEvent]] = defaultdict(list)
        for e in events:
            if e.source_message_id is not None:
                event_groups[(e.source_id, e.source_message_id, e.district_id)].append(e)

        event_deleted = 0
        affected_threat_ids: set[int] = set()
        for rows in event_groups.values():
            if len(rows) <= 1:
                continue
            rows.sort(key=lambda e: e.id)
            for extra in rows[1:]:
                affected_threat_ids.add(extra.threat_id)
                await s.delete(extra)
                event_deleted += 1
        await s.commit()

        # --- 3. Recompute fusion for affected tracks; drop any left empty ---
        threats_deleted = 0
        threats_updated = 0
        for tid in affected_threat_ids:
            t = await s.get(Threat, tid)
            if t is None:
                continue
            await s.refresh(t, ["events"])
            if not t.events:
                await s.delete(t)
                threats_deleted += 1
            else:
                await apply_fusion(s, t)
                threats_updated += 1
        await s.commit()

    print(f"raw_messages removed:  {raw_deleted}")
    print(f"threat_events removed: {event_deleted}")
    print(f"tracks recomputed:     {threats_updated}")
    print(f"tracks emptied+deleted:{threats_deleted}")


if __name__ == "__main__":
    asyncio.run(main())

"""One-off: backfill `notices.source_message_id` for rows created before that
column existed (migration 0005), so the /raw debug view can trace a raw
message forward to the notice it produced ("N82" etc).

Matches each notice to its originating raw_messages row by an EXACT
(source_id, event_time, text) triple — both were written from the same
`when`/`text` values in the same ingest call (see
pipeline/ingest.py::_make_notice), so this is not a fuzzy guess. A notice
whose match is missing or ambiguous (0 or 2+ raw messages with that exact
triple) is left untouched rather than guessed at. Safe to re-run: only
touches notices where source_message_id IS NULL.

    cd backend && .venv/bin/python scripts/backfill_notice_source_message_id.py [--dry-run]
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Notice, RawMessage  # noqa: E402


async def backfill(dry_run: bool = False) -> None:
    async with SessionLocal() as session:
        notices = list(
            await session.scalars(select(Notice).where(Notice.source_message_id.is_(None)))
        )
        matched = ambiguous = unmatched = 0
        for n in notices:
            candidates = list(
                await session.scalars(
                    select(RawMessage).where(
                        RawMessage.source_id == n.source_id,
                        RawMessage.event_time == n.event_time,
                        RawMessage.text == n.text,
                    )
                )
            )
            if len(candidates) == 1:
                matched += 1
                if not dry_run:
                    n.source_message_id = candidates[0].message_id
            elif len(candidates) == 0:
                unmatched += 1
            else:
                ambiguous += 1

        if not dry_run:
            await session.commit()

        print(
            f"notices needing backfill: {len(notices)}\n"
            f"  matched:   {matched}{' (not written — dry run)' if dry_run else ''}\n"
            f"  ambiguous: {ambiguous} (2+ raw messages with the same source/time/text — skipped)\n"
            f"  unmatched: {unmatched} (no raw message with that exact source/time/text — skipped)"
        )


if __name__ == "__main__":
    asyncio.run(backfill(dry_run="--dry-run" in sys.argv))

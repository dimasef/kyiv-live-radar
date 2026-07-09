"""Replay real captured messages through the real ingest pipeline.

Unlike simulator.py's synthetic random routes (which never reply-thread, so
they never accumulate into multi-point tracks — see geo.ts's vector logic),
this replays actual messages backfilled from the 3 production channels
(app/data/real_sample_messages.jsonl, 2026-07-05..09), preserving their
original reply chains. Real spotter narrative, real districts, real tracks,
real vectors — a faithful demo without needing Telegram credentials.

`when` passed to ingest_message is each message's ORIGINAL timestamp (not
wall-clock "now") so corroboration/gap windows behave exactly as they did on
the real feed — see eval/track_eval.py, which validated tracking accuracy
against this exact same dataset. The delay between ingesting messages is only
for visible pacing on the frontend, decoupled from that timing.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from .broadcast import broadcast_results
from .db import SessionLocal
from .ingest import ingest_message
from .models import District, Source
from .parser import DistrictMatcher

log = logging.getLogger("replay")

_DATA_FILE = Path(__file__).parent / "data" / "real_sample_messages.jsonl"

# channel_key -> display name, matching what telegram_listener would have
# created for these same channels (so a DB that's seen both replay and a real
# listener run reuses one Source row per channel, not two).
_CHANNELS = {
    "Kyiaradar": "Місто Кия | Безпека",
    "ppo_kiev": "ППО - Київ🇺🇦",
    "kiev_trevoha": "Віраж Києва",
}

_PACING_SECONDS = 0.25


async def _ensure_sources() -> dict[str, int]:
    async with SessionLocal() as s:
        existing = {x.channel_key: x for x in await s.scalars(select(Source))}
        key_to_id = {}
        for key, name in _CHANNELS.items():
            src = existing.get(key)
            if src is None:
                src = Source(channel_key=key, name=name)
                s.add(src)
                await s.flush()
            key_to_id[key] = src.id
        await s.commit()
        return key_to_id


def _load_messages() -> list[dict]:
    return [json.loads(line) for line in _DATA_FILE.read_text("utf-8").splitlines() if line.strip()]


async def run_replay() -> None:
    messages = _load_messages()
    log.info("replaying %d real captured messages", len(messages))
    key_to_source_id = await _ensure_sources()

    async with SessionLocal() as s:
        districts = list(await s.scalars(select(District)))
    matcher = DistrictMatcher(districts)

    for msg in messages:
        source_id = key_to_source_id[msg["channel_key"]]
        when = datetime.fromisoformat(msg["time"])
        async with SessionLocal() as s:
            try:
                results = await ingest_message(
                    s, text=msg["text"], matcher=matcher, when=when,
                    source_id=source_id, message_id=msg["message_id"],
                    reply_to_message_id=msg["reply_to_message_id"],
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("replay failed on message_id=%s", msg["message_id"])
                results = []
            if results:
                await broadcast_results(s, results)
        await asyncio.sleep(_PACING_SECONDS)

    log.info("replay finished — %d messages ingested", len(messages))

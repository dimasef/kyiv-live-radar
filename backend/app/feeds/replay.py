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
import os
import random
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from ..db import SessionLocal
from ..models import Source
from ..pipeline.broadcast import broadcast_results
from ..pipeline.ingest import ingest_message
from .common import build_matcher

log = logging.getLogger("replay")

# Which captured-message file to replay. Override with REPLAY_FILE to demo a
# specific event (e.g. a single night's attack) instead of the full sample.
_DEFAULT_DATA_FILE = Path(__file__).parent.parent / "data" / "real_sample_messages.jsonl"


def _data_file() -> Path:
    override = os.getenv("REPLAY_FILE")
    return Path(override) if override else _DEFAULT_DATA_FILE

# channel_key -> display name, matching what telegram_listener would have
# created for these same channels (so a DB that's seen both replay and a real
# listener run reuses one Source row per channel, not two).
_CHANNELS = {
    "Kyiaradar": "Місто Кия | Безпека",
    "ppo_kiev": "ППО - Київ🇺🇦",
    "kiev_trevoha": "Віраж Києва",
}

# Delay between broadcasting successive messages — visible pacing only (the
# `when` timestamps below preserve real tracking windows regardless). Defaults to
# 0.25s; set REPLAY_PACING_MIN/MAX (seconds) to slow it down, e.g. 3 and 5 to
# watch a night's attack unfold at ~one event every 3–5s. Equal min/max = fixed.
_PACING_MIN = float(os.getenv("REPLAY_PACING_MIN", "0.25"))
_PACING_MAX = float(os.getenv("REPLAY_PACING_MAX", str(_PACING_MIN)))


def _pacing_seconds() -> float:
    lo, hi = _PACING_MIN, max(_PACING_MIN, _PACING_MAX)
    return random.uniform(lo, hi) if hi > lo else lo


# Replaying an OLD night's messages verbatim keeps their original timestamps —
# fine for tracking windows, but the incident/track staleness sweepers run on
# wall-clock "now", so every incident instantly looks stale and fragments. Set
# REPLAY_SHIFT_TO_NOW=true to slide the whole sequence forward so its LAST
# message lands ~now (relative gaps preserved) — the attack then reads as "just
# happening" and groups into ONE incident, as it would live. Demo aid only.
_SHIFT_TO_NOW = os.getenv("REPLAY_SHIFT_TO_NOW", "false").lower() in ("1", "true", "yes")


def _time_offset(messages: list[dict]) -> timedelta:
    if not _SHIFT_TO_NOW or not messages:
        return timedelta(0)
    latest = max(datetime.fromisoformat(m["time"]) for m in messages)
    return datetime.utcnow() - latest


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
    return [json.loads(line) for line in _data_file().read_text("utf-8").splitlines() if line.strip()]


async def run_replay() -> None:
    messages = _load_messages()
    log.info("replaying %d real captured messages from %s (pacing %.2f-%.2fs)",
             len(messages), _data_file().name, _PACING_MIN, max(_PACING_MIN, _PACING_MAX))
    key_to_source_id = await _ensure_sources()
    offset = _time_offset(messages)
    if offset:
        log.info("shifting replay timestamps by %s so the sequence ends ~now", offset)

    matcher = await build_matcher()

    for msg in messages:
        source_id = key_to_source_id[msg["channel_key"]]
        when = datetime.fromisoformat(msg["time"]) + offset
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
        await asyncio.sleep(_pacing_seconds())

    log.info("replay finished — %d messages ingested", len(messages))

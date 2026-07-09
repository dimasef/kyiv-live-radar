"""Text simulator: emits realistic Ukrainian channel messages through the REAL
ingest/parse/track pipeline, so the frontend shows genuine parser output before
Telegram credentials are configured. Disable via SIMULATOR_ENABLED.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import random

from sqlalchemy import select

from .broadcast import broadcast_results
from .db import SessionLocal
from .ingest import ingest_message
from .models import District, Source, utcnow
from .parser import DistrictMatcher

log = logging.getLogger("simulator")

_msg_ids = itertools.count(5000)

_SIGHTING = [
    "🔴 {tgt} над {name}",
    "{tgt} курс на {name}",
    "{name} — чути рух, {tgt}",
    "🔴 {tgt}, {name}",
]


def _route(districts: list[District], steps: int) -> list[District]:
    start = random.choice(districts)
    route = [start]
    remaining = [d for d in districts if d.id != start.id]
    while remaining and len(route) < steps:
        last = route[-1]
        remaining.sort(key=lambda d: (d.lat - last.lat) ** 2 + (d.lon - last.lon) ** 2)
        route.append(remaining.pop(random.randint(0, min(2, len(remaining) - 1))))
    return route


async def _run_one_wave(matcher: DistrictMatcher) -> None:
    async with SessionLocal() as session:
        districts = list(await session.scalars(select(District)))
        sources = {s.channel_key: s for s in await session.scalars(select(Source))}
        if len(districts) < 3 or not sources:
            return

        keys = list(sources.keys())
        primary_key = random.choice([k for k in keys if k != "aggregator"])
        tgt = random.choice(["Шахед", "шахед", "БпЛА", "Реактивний БпЛА"])
        route = _route(districts, steps=random.randint(3, 6))

        async def emit(text, src_key, fwd=None):
            src = sources[src_key]
            mid = next(_msg_ids)
            results = await ingest_message(
                session, text=text, matcher=matcher, when=utcnow(),
                source_id=src.id, message_id=mid, forwarded_from_id=fwd,
            )
            await broadcast_results(session, results)
            return mid

        for i, d in enumerate(route):
            prefix = "Новий " if i == 0 and random.random() < 0.3 else ""
            mid = await emit(prefix + random.choice(_SIGHTING).format(tgt=tgt, name=d.name_uk),
                             primary_key)

            # A second channel corroborates the same sighting.
            if random.random() < 0.5:
                other = random.choice([k for k in keys if k not in (primary_key, "aggregator")])
                await emit(f"{tgt} {d.name_uk}, підтверджую", other)

            # Aggregator reposts the primary message (must NOT inflate corroboration).
            if random.random() < 0.3:
                await emit(f"🔁 репост: {tgt} {d.name_uk}", "aggregator", fwd=mid)

            # Occasionally a source disagrees on the target type -> conflict.
            if i > 0 and random.random() < 0.15:
                await emit(f"Балістика, {d.name_uk}! Укриття!", "shahed_watch")

            await asyncio.sleep(random.uniform(2.0, 4.0))

        # Close the wave.
        if random.random() < 0.7:
            await emit(f"Збили ціль над {route[-1].name_uk}", primary_key)
        else:
            await emit("Відбій тривоги в Києві", primary_key)


async def run_simulator() -> None:
    log.info("text simulator started (real parse/track pipeline)")
    async with SessionLocal() as session:
        districts = list(await session.scalars(select(District)))
    matcher = DistrictMatcher(districts)
    while True:
        try:
            await _run_one_wave(matcher)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("simulator wave failed")
        await asyncio.sleep(random.uniform(3.0, 6.0))

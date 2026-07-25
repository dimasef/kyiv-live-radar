from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select

from .config import settings
from .db import SessionLocal
from .domain.geometry import centroid
from .gazetteer import DISTRICTS, SOURCES
from .models import District, Source

_BOUNDARIES_FILE = Path(__file__).parent / "data" / "boundaries.json"


def _load_boundaries() -> dict:
    if _BOUNDARIES_FILE.exists():
        return json.loads(_BOUNDARIES_FILE.read_text("utf-8"))
    return {}


async def seed_sources() -> int:
    """Idempotently populate the sources table from the gazetteer."""
    async with SessionLocal() as session:
        existing = await session.scalar(select(func.count()).select_from(Source))
        if existing:
            return 0
        session.add_all(
            Source(
                channel_key=s["channel_key"],
                name=s["name"],
                trust_weight=s.get("trust_weight", 1.0),
                role=s.get("role", "spotter"),
            )
            for s in SOURCES
        )
        await session.commit()
        return len(SOURCES)


async def bootstrap_sources_from_env() -> int:
    """Idempotently seed the env channel lists (TELEGRAM_CHANNELS / ALERT_CHANNELS)
    into the sources table as active rows, so an existing deploy keeps watching the
    same channels after subscription becomes DB-driven — no manual migration.

    Runs on every startup; only inserts handles not already present (by channel_key
    or subscribe_ref), so it never resurrects a channel the operator later removed
    in /admin (removal = is_active=False, the row stays). After this one-time
    bridge the DB is the source of truth and the env lists can be cleared."""
    specs = (
        [(h, "spotter") for h in settings.telegram_channel_list]
        + [(h, "alert") for h in settings.alert_channel_list]
    )
    if not specs:
        return 0
    async with SessionLocal() as session:
        rows = list(await session.scalars(select(Source)))
        known = {r.channel_key for r in rows} | {r.subscribe_ref for r in rows if r.subscribe_ref}
        added = 0
        for handle, role in specs:
            if handle in known:
                continue
            session.add(Source(channel_key=handle, name=handle, role=role,
                               subscribe_ref=handle, is_active=True))
            known.add(handle)
            added += 1
        await session.commit()
        return added


async def seed_districts() -> int:
    """Idempotently populate the districts table from the gazetteer.

    Inserts any gazetteer entry (keyed by name_en) not already present, so a
    grown gazetteer picks up new localities on the next startup without a wipe —
    and re-syncs ALIASES on existing rows, which otherwise never reached a DB
    seeded before the alias was added (the reason prod missed «Солома!» on
    07-18 while the code had the alias). Returns the number inserted.
    """
    async with SessionLocal() as session:
        have = {d.name_en: d for d in await session.scalars(select(District))}
        boundaries = _load_boundaries()
        rows = []
        for d in DISTRICTS:
            if d["name_en"] in have:
                row = have[d["name_en"]]
                if (row.aliases or []) != d.get("aliases", []):
                    row.aliases = d.get("aliases", [])
                continue
            geom = boundaries.get(d["name_en"])
            lat, lon = d["lat"], d["lon"]
            if geom:  # use the real polygon centroid as the representative point
                lat, lon = centroid(geom)
            rows.append(District(
                name_uk=d["name_uk"],
                name_en=d["name_en"],
                lat=lat,
                lon=lon,
                aliases=d.get("aliases", []),
                boundary=geom,
            ))
        session.add_all(rows)
        await session.commit()
        return len(rows)

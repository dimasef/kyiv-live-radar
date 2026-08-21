from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import func, select

from .config import settings
from .db import SessionLocal
from .domain.geometry import centroid
from .gazetteer import DISTRICTS, SOURCES
from .models import HOME_REGION, District, Source, ThreatEvent

log = logging.getLogger("seed")

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
                region=s.get("region", HOME_REGION),
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
    and re-syncs ALIASES and REGION on existing rows, which otherwise never
    reached a DB seeded before the value changed (the reason prod missed
    «Солома!» on 07-18 while the code had the alias; re-labelling an entry's
    region would go the same way). Returns the number inserted.
    """
    async with SessionLocal() as session:
        have = {d.name_en: d for d in await session.scalars(select(District))}
        boundaries = _load_boundaries()
        rows = []
        for d in DISTRICTS:
            region = d.get("region", HOME_REGION)
            region_only = bool(d.get("region_only", False))
            if d["name_en"] in have:
                row = have[d["name_en"]]
                if (row.aliases or []) != d.get("aliases", []):
                    row.aliases = d.get("aliases", [])
                if row.region != region:
                    row.region = region
                if row.region_only != region_only:
                    row.region_only = region_only
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
                region=region,
                region_only=region_only,
            ))
        session.add_all(rows)
        await session.commit()
        await _retire_orphan_districts(session)
        return len(rows)


async def _retire_orphan_districts(session) -> None:
    """Drop DB rows for entries no longer in the gazetteer.

    Seeding only ever inserted and updated, so an entry REMOVED from
    `gazetteer.py` lived on in the DB and kept matching. Live case, 2026-08-21:
    a Kyiv «ТЕЦ» was seeded from a work-in-progress edit and then deleted from
    the file; the row stayed, and because "тец" had meanwhile become a
    whole-word alias its three-letter name matched on its own — pinning every
    bare Kyiv «ТЕЦ» onto a plant the gazetteer no longer claimed.

    Only rows nothing references are removed. A district that already carries
    sightings is history, not a mistake: deleting it would orphan those events
    (and violate the FK), so it is logged for the operator instead of dropped.
    """
    keep = {d["name_en"] for d in DISTRICTS}
    orphans = [d for d in await session.scalars(select(District)) if d.name_en not in keep]
    if not orphans:
        return
    used = set(
        await session.scalars(
            select(ThreatEvent.district_id).where(
                ThreatEvent.district_id.in_([d.id for d in orphans])
            )
        )
    )
    for d in orphans:
        if d.id in used:
            log.warning(
                "district %r (id=%s) is gone from the gazetteer but has sightings — kept",
                d.name_uk, d.id,
            )
            continue
        log.info("retiring district %r (id=%s): no longer in the gazetteer", d.name_uk, d.id)
        await session.delete(d)
    await session.commit()

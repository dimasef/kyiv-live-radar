"""Directional threat-axis lifecycle — the origin analogue of alerts.py.

`apply_axis_signal` is idempotent-with-fusion: repeat callouts of the same
inbound direction fold into ONE axis (bumping corroboration only for a genuinely
new source), an axis promotes unverified->corroborated once
`axis_min_sources` independent sources agree, and the sweeper expires it after
`axis_ttl_minutes` of silence. Deliberately thin — one function, no
registry/plugin framework (see CLAUDE.md "чого не робити").

An axis is NOT a map point. It carries a compass sector + optional curated
origin key; the frontend draws a screen-edge wedge along the bearing
(origins.bearing_for). Never a Kyiv district.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload  # noqa: F401  (kept for symmetry/future eager loads)

from ..config import settings
from ..models import ThreatAxis

log = logging.getLogger("axes")


@dataclass
class AxisSignal:
    sector: str                    # compass octant (origins.SECTORS)
    target_type: str               # 'ballistic' | 'missile' | 'shahed' | ... | 'unknown'
    when: datetime
    origin_key: str | None = None  # curated origin (origins.ORIGIN_KEYS) if a toponym was named
    source_dedup_key: str = ""     # independent-source identity (see fusion._origin_keys)
    raw_id: int | None = None


def _family(target_type: str) -> str:
    """Same family collapse as fusion._family — a ballistic axis and a bare
    missile axis on the same bearing are the same inbound threat at different
    specificity, so they fuse rather than splitting into two wedges."""
    if target_type in ("missile", "ballistic"):
        return "missile"
    if target_type in ("shahed", "jet_drone"):
        return "drone"
    return target_type


def _within(a: datetime, b: datetime, gap: timedelta) -> bool:
    an = a.replace(tzinfo=None) if a.tzinfo is not None else a
    bn = b.replace(tzinfo=None) if b.tzinfo is not None else b
    return abs((bn - an).total_seconds()) <= gap.total_seconds()


def _upgrade_type(current: str, new: str) -> str:
    """Mirror ingest._upgrade_type: unknown adopts any stated type; a generic
    missile upgrades to ballistic; never cross families."""
    if current == "unknown":
        return new
    if {current, new} == {"missile", "ballistic"}:
        return "ballistic"
    return current


async def _find_open_matching(session, signal: AxisSignal) -> ThreatAxis | None:
    """The freshest still-open axis on the same sector + target-family whose last
    callout is within the fusion window — the one this signal corroborates."""
    window = timedelta(minutes=settings.axis_fusion_window_minutes)
    fam = _family(signal.target_type)
    stmt = (
        select(ThreatAxis)
        .where(ThreatAxis.expires_at.is_(None), ThreatAxis.sector == signal.sector)
        .order_by(ThreatAxis.created_at.desc())
    )
    for axis in await session.scalars(stmt):
        if _family(axis.target_type) != fam and fam != "unknown" and _family(axis.target_type) != "unknown":
            continue
        if _within(axis.last_seen_at, signal.when, window):
            return axis
    return None


async def apply_axis_signal(session, signal: AxisSignal) -> ThreatAxis | None:
    """Fold `signal` into an open matching axis, or open a new one. Returns the
    affected axis (created or updated) so the caller broadcasts its fresh state;
    None only when the axis layer is disabled."""
    if not settings.axis_enabled:
        return None
    axis = await _find_open_matching(session, signal)
    if axis is None:
        axis = ThreatAxis(
            created_at=signal.when,
            last_seen_at=signal.when,
            target_type=signal.target_type,
            origin_key=signal.origin_key,
            sector=signal.sector,
            status="unverified",
            corroboration_count=1,
            origin_keys_seen=[signal.source_dedup_key] if signal.source_dedup_key else [],
            raw_ids=[signal.raw_id] if signal.raw_id is not None else [],
        )
        session.add(axis)
        await session.commit()
        log.info("axis %s opened (sector=%s type=%s origin=%s)",
                 axis.id, axis.sector, axis.target_type, axis.origin_key)
        return axis

    axis.last_seen_at = signal.when
    axis.target_type = _upgrade_type(axis.target_type, signal.target_type)
    if axis.origin_key is None and signal.origin_key is not None:
        axis.origin_key = signal.origin_key
    if signal.source_dedup_key and signal.source_dedup_key not in axis.origin_keys_seen:
        axis.origin_keys_seen = [*axis.origin_keys_seen, signal.source_dedup_key]
        axis.corroboration_count = len(axis.origin_keys_seen)
    if signal.raw_id is not None and signal.raw_id not in axis.raw_ids:
        axis.raw_ids = [*axis.raw_ids, signal.raw_id]
    if axis.corroboration_count >= settings.axis_min_sources and axis.status == "unverified":
        axis.status = "corroborated"
        log.info("axis %s corroborated (%d sources)", axis.id, axis.corroboration_count)
    await session.commit()
    return axis


async def close_stale_axes(session, now: datetime) -> list[ThreatAxis]:
    """Expire axes with no new callout for `axis_ttl_minutes` — a direction is a
    fleeting cue, not a standing state."""
    ttl = timedelta(minutes=settings.axis_ttl_minutes)
    open_axes = list(await session.scalars(select(ThreatAxis).where(ThreatAxis.expires_at.is_(None))))
    expired = [a for a in open_axes if not _within(a.last_seen_at, now, ttl)]
    for a in expired:
        a.expires_at = now
        a.status = "expired"
    if expired:
        await session.commit()
    return expired

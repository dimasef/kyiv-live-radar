"""Rebuild every track from the stored raw messages through the current pipeline:
preview the scope first, then apply it under the ingest lock."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

from ...auth.deps import require_admin
from ...domain.districts import citywide_district_id
from ...domain.journal import KYIV, build_journal
from ...models import (
    Alert,
    Incident,
    RawMessage,
    Threat,
    ThreatEvent,
    User,
)
from ...pipeline import reprocess as reprocess_mod
from ...pipeline.ingest import ingest_lock
from ...schemas import (
    ReprocessApplyIn,
    ReprocessPreviewOut,
    ReprocessResultOut,
)
from ..deps import _attack_active

router = APIRouter()


async def _reprocess_summary(s) -> dict:
    """Totals + recent per-day target/track counts (reuses the journal
    aggregation, so it matches what the operator sees on /journal)."""
    tracks = await s.scalar(select(func.count()).select_from(Threat))
    events = await s.scalar(select(func.count()).select_from(ThreatEvent))
    incidents = await s.scalar(select(func.count()).select_from(Incident))
    today = datetime.now(UTC).astimezone(KYIV).date()
    start = today - timedelta(days=20)
    threats = list(await s.scalars(select(Threat)))
    incs = list(await s.scalars(select(Incident)))
    alerts = list(await s.scalars(select(Alert).where(Alert.scope == "city")))
    district_events = (
        await s.execute(
            select(ThreatEvent.event_time, ThreatEvent.district_id, Threat.kind == "impact")
            .join(Threat, ThreatEvent.threat_id == Threat.id)
            .where(Threat.closed_reason.is_distinct_from("dismissed"))
        )
    ).all()
    sentinel = await citywide_district_id(s)
    stats = build_journal(
        start, today, threats=threats, incidents=incs, alerts=alerts,
        district_events=district_events, sentinel_district_id=sentinel,
    )
    return {
        "tracks": tracks or 0,
        "events": events or 0,
        "incidents": incidents or 0,
        "days": [
            {"date": d.date, "target_count": d.target_count, "track_count": d.track_count}
            for d in stats
        ],
    }

@router.get("/admin/reprocess/preview", response_model=ReprocessPreviewOut)
async def admin_reprocess_preview(_admin: User = Depends(require_admin)):
    """Pre-flight scope: how many raw messages will replay, the current counts
    that will be rebuilt, and whether an attack is active (a reprocess would be
    ill-timed). Read-only. Uses reprocess's own SessionLocal so it reads exactly
    the DB the apply would rebuild."""
    async with reprocess_mod.SessionLocal() as s:
        raw_count = await s.scalar(select(func.count()).select_from(RawMessage))
        current = await _reprocess_summary(s)
        attack = await _attack_active(s)
    return ReprocessPreviewOut(raw_messages=raw_count or 0, current=current, attack_active=attack)


@router.post("/admin/reprocess/apply", response_model=ReprocessResultOut)
async def admin_reprocess_apply(
    body: ReprocessApplyIn,
    _admin: User = Depends(require_admin),
):
    """Wipe + rebuild all tracks/incidents from raw_messages through the current
    pipeline. Held under `ingest_lock` so the live listener can't ingest into a
    half-rebuilt DB (messages queue behind it and process after). Refuses while
    an attack is active unless `force`. raw_messages are preserved, so a
    reprocess is repeatable."""
    async with reprocess_mod.SessionLocal() as s:
        if not body.force and await _attack_active(s):
            raise HTTPException(
                status_code=409,
                detail="attack active — reprocess now would disrupt live tracking (pass force)",
            )
        before = await _reprocess_summary(s)
    async with ingest_lock:
        result = await reprocess_mod.run_reprocess(no_llm=body.no_llm)
    async with reprocess_mod.SessionLocal() as s:
        after = await _reprocess_summary(s)
    return ReprocessResultOut(before=before, after=after, result=result)


# --- Sources / channels management (admin) --------------------------------
# The DB's active Sources ARE the live channel list (feeds/telegram.py reads
# them); mutations here signal the listener to reconnect and re-subscribe.

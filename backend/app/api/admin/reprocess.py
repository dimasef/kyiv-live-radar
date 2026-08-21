"""Rebuild every track from the stored raw messages through the current pipeline:
preview the scope first, then apply it under the ingest lock."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from ...auth.deps import require_admin
from ...domain.journal import KYIV, build_journal
from ...models import (
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
from ..journal_window import load_journal_window

router = APIRouter()


async def _reprocess_summary(s) -> dict:
    """Totals + recent per-day target/track counts (reuses the journal
    aggregation, so it matches what the operator sees on /journal).

    The per-day part goes through the same bounded loader the calendar uses.
    It used to read `threats`, `incidents` and the WHOLE `threat_events` table
    with no time filter to build 20 days of rows — on every preview, and twice
    per apply."""
    tracks = await s.scalar(select(func.count()).select_from(Threat))
    events = await s.scalar(select(func.count()).select_from(ThreatEvent))
    incidents = await s.scalar(select(func.count()).select_from(Incident))
    today = datetime.now(UTC).astimezone(KYIV).date()
    start = today - timedelta(days=20)
    w = await load_journal_window(s, start, today, today)
    stats = build_journal(
        start, today, threats=w.threats, incidents=w.incidents, alerts=w.alerts,
        district_events=w.district_events, sentinel_district_id=w.sentinel,
        hide_impacts_from=w.hide_impacts_from,
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
async def admin_reprocess_preview(
    last: int | None = Query(None, ge=1),
    _admin: User = Depends(require_admin),
):
    """Pre-flight scope: how many raw messages will replay, the current counts
    that will be rebuilt, and whether an attack is active (a reprocess would be
    ill-timed). Read-only. Uses reprocess's own SessionLocal so it reads exactly
    the DB the apply would rebuild.

    With `last=N`, also reports the real scope of that tail — the widened cutoff
    and the message count it covers, so the operator sees what "останні N" will
    actually touch before running it."""
    async with reprocess_mod.SessionLocal() as s:
        raw_count = await s.scalar(select(func.count()).select_from(RawMessage))
        current = await _reprocess_summary(s)
        attack = await _attack_active(s)
        scope_from = await reprocess_mod.scope_cutoff(s, last) if last else None
        scope_messages = (
            await s.scalar(
                select(func.count())
                .select_from(RawMessage)
                .where(RawMessage.event_time >= scope_from)
            )
            if scope_from is not None
            else None
        )
    return ReprocessPreviewOut(
        raw_messages=raw_count or 0,
        current=current,
        attack_active=attack,
        scope_messages=scope_messages,
        scope_from=scope_from,
    )


@router.post("/admin/reprocess/apply", response_model=ReprocessResultOut)
async def admin_reprocess_apply(
    body: ReprocessApplyIn,
    _admin: User = Depends(require_admin),
):
    """Wipe + rebuild tracks/incidents from raw_messages through the current
    pipeline. Held under `ingest_lock` so the live listener can't ingest into a
    half-rebuilt DB (messages queue behind it and process after). Refuses while
    an attack is active unless `force`. raw_messages are preserved, so a
    reprocess is repeatable.

    `last` limits the rebuild to the tail of the log (see run_reprocess); the
    default still rebuilds everything."""
    async with reprocess_mod.SessionLocal() as s:
        if not body.force and await _attack_active(s):
            raise HTTPException(
                status_code=409,
                detail="attack active — reprocess now would disrupt live tracking (pass force)",
            )
        before = await _reprocess_summary(s)
    async with ingest_lock:
        result = await reprocess_mod.run_reprocess(no_llm=body.no_llm, last=body.last)
    async with reprocess_mod.SessionLocal() as s:
        after = await _reprocess_summary(s)
    return ReprocessResultOut(before=before, after=after, result=result)


# --- Sources / channels management (admin) --------------------------------
# The DB's active Sources ARE the live channel list (feeds/telegram.py reads
# them); mutations here signal the listener to reconnect and re-subscribe.

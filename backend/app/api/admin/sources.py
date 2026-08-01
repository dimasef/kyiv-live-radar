"""Monitored-channel (Source) management — the DB's active rows ARE the live
channel list the Telethon listener subscribes to."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.deps import require_admin
from ...db import get_session
from ...domain.sources import delete_source_cascade, upsert_source
from ...feeds.telegram import request_listener_reload
from ...models import (
    Source,
    User,
)
from ...schemas import (
    SourceAdminOut,
    SourceDeleteOut,
    SourceIn,
    SourceStatsOut,
    SourceUpdateIn,
)
from ..deps import _attack_active
from ..source_stats import SourceStats, compute_source_stats

router = APIRouter()


def _source_admin_out(src: Source, stats: dict[int, SourceStats]) -> SourceAdminOut:
    st = stats.get(src.id) or SourceStats()
    return SourceAdminOut(
        id=src.id,
        channel_key=src.channel_key,
        name=src.name,
        subscribe_ref=src.subscribe_ref,
        role=src.role,
        is_active=src.is_active,
        trust_weight=src.trust_weight,
        last_listener_error=src.last_listener_error,
        created_at=src.created_at,
        stats=SourceStatsOut(
            messages_total=st.messages_total,
            messages_processed=st.messages_processed,
            events_produced=st.events_produced,
            llm_fallback_rate=st.llm_fallback_rate,
            coverage_rate=st.coverage_rate,
            correction_rate=st.correction_rate,
            conflict_share=st.conflict_share,
            quality_score=st.quality_score,
            last_message_at=st.last_message_at,
        ),
    )


@router.get("/admin/sources", response_model=list[SourceAdminOut])
async def admin_list_sources(
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """Every source with its on-demand quality stats — active channels first,
    then by name. Inactive rows are kept (removal is a soft deactivate) so the
    operator can re-enable or inspect a channel's history."""
    stats = await compute_source_stats(session)
    rows = list(await session.scalars(select(Source)))
    rows.sort(key=lambda s: (not s.is_active, s.name.lower()))
    return [_source_admin_out(s, stats) for s in rows]


@router.post("/admin/sources", response_model=SourceAdminOut)
async def admin_add_source(
    body: SourceIn,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Add (or reactivate) a channel and tell the listener to re-subscribe. Whether
    it actually starts delivering shows up as message counts / last_listener_error
    on the next connect."""
    src = await upsert_source(
        session,
        subscribe_ref=body.subscribe_ref,
        name=body.name,
        role=body.role,
        trust_weight=body.trust_weight,
        user_id=admin.id,
    )
    await session.commit()
    request_listener_reload()
    stats = await compute_source_stats(session)
    return _source_admin_out(src, stats)


@router.patch("/admin/sources/{source_id}", response_model=SourceAdminOut)
async def admin_update_source(
    source_id: int,
    body: SourceUpdateIn,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """Edit a source's name / role / trust_weight / active flag. Only a change that
    affects what's watched (role or is_active) triggers a listener reload."""
    src = await session.get(Source, source_id)
    if src is None:
        raise HTTPException(status_code=404, detail="source not found")
    reload_needed = False
    if body.name is not None:
        src.name = body.name
    if body.role is not None and body.role != src.role:
        src.role = body.role
        reload_needed = True
    if body.trust_weight is not None:
        src.trust_weight = body.trust_weight
    if body.is_active is not None and body.is_active != src.is_active:
        src.is_active = body.is_active
        reload_needed = True
    await session.commit()
    if reload_needed:
        request_listener_reload()
    stats = await compute_source_stats(session)
    return _source_admin_out(src, stats)


@router.post("/admin/sources/{source_id}/deactivate", response_model=SourceAdminOut)
async def admin_deactivate_source(
    source_id: int,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """Remove a channel from the live feed (soft — the row stays, since
    raw_messages/threat_events reference it and its history stays queryable)."""
    return await _set_source_active(session, source_id, active=False)


@router.post("/admin/sources/{source_id}/activate", response_model=SourceAdminOut)
async def admin_activate_source(
    source_id: int,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    return await _set_source_active(session, source_id, active=True)


async def _set_source_active(session: AsyncSession, source_id: int, *, active: bool) -> SourceAdminOut:
    src = await session.get(Source, source_id)
    if src is None:
        raise HTTPException(status_code=404, detail="source not found")
    if src.is_active != active:
        src.is_active = active
        await session.commit()
        request_listener_reload()
    stats = await compute_source_stats(session)
    return _source_admin_out(src, stats)


@router.delete("/admin/sources/{source_id}", response_model=SourceDeleteOut)
async def admin_delete_source(
    source_id: int,
    force: bool = Query(False, description="Delete even while an attack is active"),
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """HARD-delete a channel AND all of its stored data (raw_messages, notices,
    threat_events), repairing the tracks/incidents it touched — irreversible,
    unlike deactivate. Refused while an attack is active (the graph surgery would
    disrupt live tracking) unless `force`."""
    if not force and await _attack_active(session):
        raise HTTPException(
            status_code=409,
            detail="attack active — deleting a source now would disrupt live tracking (pass force)",
        )
    result = await delete_source_cascade(session, source_id)
    if result is None:
        raise HTTPException(status_code=404, detail="source not found")
    request_listener_reload()
    return SourceDeleteOut(**result)

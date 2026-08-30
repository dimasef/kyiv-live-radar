"""Raw-message debug views (/raw): cursor-paginated list, count, export, sources,
and aggregate LLM usage."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...auth.deps import require_admin
from ...config import settings
from ...db import get_session
from ...models import (
    RawMessage,
    Region,
    Source,
    User,
    utcnow,
)
from ...schemas import (
    RawCountOut,
    RawExportOut,
    RawLlmStatsOut,
    RawMessagesPage,
    RawSourceOut,
)
from ...timeutil import kyiv_day_start, kyiv_month_start
from ..raw_query import apply_raw_filters, serialize_raw_rows

router = APIRouter()


@router.get("/raw_messages", response_model=RawMessagesPage)
async def raw_messages(
    limit: int = Query(50, ge=1, le=200),
    before_id: int | None = Query(None, description="Return rows with id < this (cursor)"),
    q: str | None = Query(
        None,
        description="Substring search over message text, OR one/more T{id}/M{id}/N{id} "
        "codes (the same dev badges shown in the feed) to look up by exact match instead",
    ),
    outcome: str | None = Query(
        None, description="'event' = became a sighting or notice; 'suppressed' = everything else"
    ),
    llm: str | None = Query(
        None, description="'yes'|'no' — whether the LLM fallback was called (NULL rows excluded)"
    ),
    source_id: list[int] | None = Query(
        None, description="Filter to these monitored channels (repeat the param; empty = all)"
    ),
    region: list[Region] | None = Query(
        None,
        description="Filter to these watched regions (repeat the param; empty = all): "
        "messages that produced a sighting in one of them, plus ones that produced "
        "nothing and came from one of their channels",
    ),
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """Every ingested message verbatim, INCLUDING ones the parser suppressed
    or couldn't localize — a debug view onto the pipeline, distinct from
    /events/recent (which only shows messages that became a live sighting).
    Cursor-paginated (before_id) newest-first — raw_messages can run to tens
    of thousands of rows, too many to offset-paginate cheaply."""
    stmt = (
        select(RawMessage)
        .options(selectinload(RawMessage.source))
        .order_by(RawMessage.id.desc())
        .limit(limit)
    )
    if before_id is not None:
        stmt = stmt.where(RawMessage.id < before_id)
    stmt = apply_raw_filters(stmt, q=q, outcome=outcome, llm=llm,
                             source_ids=source_id, regions=region)
    rows = list(await session.scalars(stmt))
    items = await serialize_raw_rows(session, rows)
    next_before_id = rows[-1].id if len(rows) == limit else None
    return RawMessagesPage(items=items, next_before_id=next_before_id)


@router.get("/raw_messages/count", response_model=RawCountOut)
async def raw_messages_count(
    q: str | None = Query(None),
    outcome: str | None = Query(None),
    llm: str | None = Query(None),
    source_id: list[int] | None = Query(None),
    region: list[Region] | None = Query(None),
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """How many raw messages match the current filter set — powers the
    "показано N з M" counter on /raw without paging through everything."""
    stmt = apply_raw_filters(
        select(func.count()).select_from(RawMessage),
        q=q, outcome=outcome, llm=llm, source_ids=source_id, regions=region,
    )
    total = await session.scalar(stmt)
    return RawCountOut(count=total or 0)


# Guard rail: a filtered export of the whole corpus could be tens of thousands
# of rows. Cap it and flag truncation so a partial export never reads as
# complete. Keeps the MOST RECENT matches when it bites (see ordering below).
_RAW_EXPORT_CAP = 5000


@router.get("/raw_messages/export", response_model=RawExportOut)
async def raw_messages_export(
    q: str | None = Query(None),
    outcome: str | None = Query(None),
    llm: str | None = Query(None),
    source_id: list[int] | None = Query(None),
    region: list[Region] | None = Query(None),
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """Every message matching the current filter (up to _RAW_EXPORT_CAP), for
    offline analysis. Returned oldest-first so the export reads as a sequence
    of events; the frontend wraps these in a JSON envelope with the human
    filter description before download."""
    stmt = (
        select(RawMessage)
        .options(selectinload(RawMessage.source))
        .order_by(RawMessage.id.desc())
        .limit(_RAW_EXPORT_CAP)
    )
    stmt = apply_raw_filters(stmt, q=q, outcome=outcome, llm=llm,
                             source_ids=source_id, regions=region)
    rows = list(await session.scalars(stmt))
    truncated = len(rows) == _RAW_EXPORT_CAP
    rows.reverse()  # newest-first fetch (so truncation keeps recent) -> chronological output
    items = await serialize_raw_rows(session, rows)
    return RawExportOut(messages=items, truncated=truncated)


@router.get("/raw_messages/sources", response_model=list[RawSourceOut])
async def raw_messages_sources(
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """Channels that actually have stored raw messages, for the /raw channel
    filter dropdown. DB-driven now (subscription moved off the env lists), so it
    lists every source with data — active or not — instead of the env-configured
    set, which is empty once TELEGRAM_CHANNELS/ALERT_CHANNELS are cleared."""
    with_messages = select(RawMessage.source_id).where(RawMessage.source_id.is_not(None))
    rows = await session.scalars(
        select(Source).where(Source.id.in_(with_messages)).order_by(Source.name)
    )
    return [
        RawSourceOut(
            id=s.id,
            name=s.name,
            regions=[s.region, *(r for r in (s.extra_regions or []) if r != s.region)],
        )
        for s in rows
    ]


@router.get("/raw_messages/llm_stats", response_model=RawLlmStatsOut)
async def raw_messages_llm_stats(
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """Aggregate LLM fallback usage across ALL raw messages — total calls,
    tokens, and cost, for the analytics strip on /raw. Unfiltered (ignores
    search/outcome filters) so it always reads as "overall spend", not
    "spend within the current view". Also reports spend for the current
    Kyiv-local day/month against the same caps `pipeline.triage.llm_spend_ok`
    gates the fallback on, so the admin can see how close to the budget the
    live pipeline is."""
    row = (
        await session.execute(
            select(
                func.count(RawMessage.id),
                func.coalesce(func.sum(RawMessage.llm_input_tokens), 0),
                func.coalesce(func.sum(RawMessage.llm_output_tokens), 0),
                func.coalesce(func.sum(RawMessage.llm_cost_usd), 0.0),
            ).where(RawMessage.llm_attempted.is_(True))
        )
    ).one()
    calls, input_tokens, output_tokens, cost_usd = row

    # Same window as the budget guard in pipeline/triage.py — spend is measured
    # by when we paid (`ingested_at`), over the Kyiv-local day, or the number
    # shown here would not be the number the cap enforces.
    now = utcnow()
    day_start = kyiv_day_start(now)
    month_start = kyiv_month_start(now)
    day_spend = await session.scalar(
        select(func.coalesce(func.sum(RawMessage.llm_cost_usd), 0.0)).where(
            RawMessage.ingested_at >= day_start
        )
    )
    month_spend = await session.scalar(
        select(func.coalesce(func.sum(RawMessage.llm_cost_usd), 0.0)).where(
            RawMessage.ingested_at >= month_start
        )
    )

    return RawLlmStatsOut(
        calls=calls,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        day_spend_usd=day_spend or 0.0,
        day_budget_usd=settings.llm_daily_budget_usd,
        month_spend_usd=month_spend or 0.0,
        month_budget_usd=settings.llm_monthly_budget_usd,
    )

"""Turn admin corrections + coverage gaps into parser accuracy: surface the
messages that never localized, and show whether the current parser has retired
each harvested correction."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.deps import require_admin
from ...db import get_session
from ...domain.corrections import (
    parser_agrees,
)
from ...feeds.common import build_matcher
from ...models import (
    District,
    ParserCorrection,
    User,
)
from ...schemas import (
    CorrectionOut,
    CoverageGapOut,
)
from ..coverage import find_coverage_gaps

router = APIRouter()


@router.get("/admin/coverage_gaps", response_model=list[CoverageGapOut])
async def admin_coverage_gaps(
    limit: int = Query(50, ge=1, le=1000),
    scan: int = Query(800, ge=50, le=20000),
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """Recent threat-flavored messages the parser couldn't pin to a district —
    the coverage-gap queue (usually a missing gazetteer entry). `scan` widens
    the raw-message window behind it; the export path asks for a bigger one
    than the on-screen list does."""
    matcher = await build_matcher(session)
    return await find_coverage_gaps(session, matcher, limit=limit, scan=scan)


@router.get("/admin/corrections", response_model=list[CorrectionOut])
async def admin_corrections(
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """Harvested corrections + whether the CURRENT parser already agrees — so
    the operator sees which mistakes are retired vs still reproduced."""
    matcher = await build_matcher(session)
    id_to_en = {d.id: d.name_en for d in await session.scalars(select(District))}
    rows = list(
        await session.scalars(
            select(ParserCorrection).order_by(ParserCorrection.created_at.desc()).limit(limit)
        )
    )
    out = []
    for c in rows:
        agrees, _ = parser_agrees(c, matcher, id_to_en)
        out.append(
            CorrectionOut(
                id=c.id,
                raw_message_id=c.raw_message_id,
                text=c.text,
                kind=c.kind,
                expected=c.expected or {},
                origin=c.origin,
                created_at=c.created_at,
                resolved=agrees,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Admin-triggered reprocess — apply the CURRENT parser to all stored raw
# messages without the REPROCESS_ON_BOOT env+restart footgun. Guarded: runs
# under the ingest lock (never races the live listener) and refuses mid-attack
# by default. Returns a before/after diff so the operator sees the effect.
# ---------------------------------------------------------------------------

"""Turn admin corrections + coverage gaps into parser accuracy: surface the
messages that never localized, capture toponym candidates, and show whether
the current parser has retired each harvested correction."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
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
    GazetteerCandidate,
    ParserCorrection,
    RawMessage,
    User,
)
from ...schemas import (
    CorrectionOut,
    CoverageGapOut,
    GazetteerCandidateIn,
    GazetteerCandidateOut,
    GazetteerCandidateStatusIn,
)
from ..coverage import find_coverage_gaps

router = APIRouter()


@router.get("/admin/coverage_gaps", response_model=list[CoverageGapOut])
async def admin_coverage_gaps(
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """Recent threat-flavored messages the parser couldn't pin to a district —
    the coverage-gap queue (usually a missing gazetteer entry)."""
    matcher = await build_matcher(session)
    return await find_coverage_gaps(session, matcher, limit=limit)


@router.post("/admin/gazetteer_candidates", response_model=GazetteerCandidateOut)
async def admin_add_gazetteer_candidate(
    body: GazetteerCandidateIn,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Capture a toponym candidate from a gap — NOT a live gazetteer edit; that
    stays a reviewed code step with a stem-collision sweep (CLAUDE.md)."""
    text = ""
    if body.raw_message_id is not None:
        raw = await session.get(RawMessage, body.raw_message_id)
        if raw is None:
            raise HTTPException(status_code=400, detail="raw message not found")
        text = raw.text
    cand = GazetteerCandidate(
        raw_message_id=body.raw_message_id,
        text=text,
        suggested_name=body.suggested_name,
        note=body.note,
        created_by_user_id=admin.id,
    )
    session.add(cand)
    await session.commit()
    return cand


@router.get("/admin/gazetteer_candidates", response_model=list[GazetteerCandidateOut])
async def admin_list_gazetteer_candidates(
    status: str | None = Query(None, description="Filter by status"),
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    stmt = select(GazetteerCandidate).order_by(GazetteerCandidate.created_at.desc())
    if status is not None:
        stmt = stmt.where(GazetteerCandidate.status == status)
    return list(await session.scalars(stmt))


@router.patch("/admin/gazetteer_candidates/{candidate_id}", response_model=GazetteerCandidateOut)
async def admin_update_gazetteer_candidate(
    candidate_id: int,
    body: GazetteerCandidateStatusIn,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    cand = await session.get(GazetteerCandidate, candidate_id)
    if cand is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    cand.status = body.status
    await session.commit()
    return cand


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

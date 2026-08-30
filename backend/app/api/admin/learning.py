"""Turn admin corrections + coverage gaps into parser accuracy: surface the
messages that never localized, and show whether the current parser has retired
each harvested correction."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, select
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
    ToponymDismissal,
    User,
)
from ...parsing import normalize
from ...schemas import (
    CorrectionOut,
    CoverageCandidateOut,
    CoverageGapOut,
    ToponymDismissalIn,
)
from ..coverage import find_coverage_gaps, find_toponym_candidates

router = APIRouter()


@router.get("/admin/coverage_gaps", response_model=list[CoverageGapOut])
async def admin_coverage_gaps(
    limit: int = Query(50, ge=1, le=1000),
    scan: int = Query(800, ge=50, le=20000),
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """Recent messages the parser couldn't pin to a district that still name an
    unknown word — the coverage-gap queue (usually a missing gazetteer entry).
    `scan` widens the raw-message window behind it; the export path asks for a
    bigger one than the on-screen list does."""
    matcher = await build_matcher(session)
    return await find_coverage_gaps(session, matcher, limit=limit, scan=scan)


@router.get("/admin/coverage_candidates", response_model=list[CoverageCandidateOut])
async def admin_coverage_candidates(
    limit: int = Query(60, ge=1, le=500),
    scan: int = Query(2000, ge=50, le=20000),
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """The gaps above, aggregated into unknown place-names ranked by how often
    each occurs — the list to geocode from. Scans deeper than the message view
    by default, because a candidate's whole signal is that it repeats."""
    matcher = await build_matcher(session)
    return await find_toponym_candidates(session, matcher, limit=limit, scan=scan)


@router.get("/admin/coverage_candidates/dismissed", response_model=list[str])
async def admin_dismissed_toponyms(
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """The words the operator has ruled out, so the console can show them and
    offer to put one back."""
    return sorted(await session.scalars(select(ToponymDismissal.word)))


@router.post("/admin/coverage_candidates/dismiss", response_model=list[str])
async def admin_dismiss_toponym(
    body: ToponymDismissalIn,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Mark one candidate as «не прогалина». It disappears from the ranking and
    from the message rows admitted for it alone, permanently and for good — the
    same judgement the curated lists in `parsing/toponyms.py` encode, made by
    hand instead of by deploy.

    Idempotent, and matched WHOLE: unlike the stem lists, a dismissal can never
    shadow a real name that merely starts with the same letters.
    """
    word = normalize(body.name).strip()
    if word and not await session.scalar(
        select(ToponymDismissal).where(ToponymDismissal.word == word)
    ):
        session.add(ToponymDismissal(word=word, created_by_user_id=admin.id))
        await session.commit()
    return sorted(await session.scalars(select(ToponymDismissal.word)))


@router.delete("/admin/coverage_candidates/dismiss/{word}", response_model=list[str])
async def admin_restore_toponym(
    word: str,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """Undo a dismissal — the word ranks again from the next scan."""
    await session.execute(
        delete(ToponymDismissal).where(ToponymDismissal.word == normalize(word).strip())
    )
    await session.commit()
    return sorted(await session.scalars(select(ToponymDismissal.word)))


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

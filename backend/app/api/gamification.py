"""Gamification — collectible-card analysis of targets.

An opt-in coping mechanic (off by default client-side): a logged-in user can
"analyse" a target on the map and receive one of a fixed deck of collectible
cards. Every route requires authentication (cards belong to accounts). No
router-level prefix — paths are written in full, matching app/api/routes.py.

Scarcity rule (operator decision): a target yields at most two analyses total,
one per kind ('track' while it flies, 'remains' once destroyed), claimed
globally first-come-first-served. The `UniqueConstraint(threat_id, kind)` on
`threat_analyses` is the enforcement point — a losing racer gets a 409, not a
duplicate card.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import get_current_user
from ..db import get_session
from ..domain.cards import CARD_COUNT, STALE_AFTER, draw_card, eligible_kind_for
from ..models import (
    Threat,
    ThreatAnalysis,
    ThreatEvent,
    User,
    utcnow,
)
from ..schemas import (
    AnalyzeIn,
    AnalyzeOut,
    CardCountOut,
    CollectionOut,
    GamificationPrefIn,
    GamificationPrefOut,
    ThreatAnalysisStateOut,
)
from ..timeutil import within
from .deps import are_friends

gamification_router = APIRouter(tags=["gamification"])


@gamification_router.post("/analysis", response_model=AnalyzeOut)
async def analyze_target(
    body: AnalyzeIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    # No `kind` check here: AnalyzeIn.kind is a Literal, so an unknown value is
    # rejected by request validation (422) before this handler runs.
    threat = await session.get(Threat, body.threat_id)
    if threat is None:
        raise HTTPException(status_code=404, detail="Ціль не знайдено")
    if not eligible_kind_for(threat, body.kind):
        # The client shouldn't have offered the button; a stale one lands here.
        raise HTTPException(status_code=409, detail="Ця ціль зараз недоступна для аналізу")

    # Block stale targets (>12h since last seen) — the mechanic tracks the LIVE
    # picture, not the archive. Reference is the latest event, else track start.
    last_seen = await session.scalar(
        select(func.max(ThreatEvent.event_time)).where(ThreatEvent.threat_id == threat.id)
    )
    if not within(utcnow(), last_seen or threat.created_at, STALE_AFTER):
        raise HTTPException(status_code=409, detail="Ціль застаріла — аналіз недоступний")

    row = ThreatAnalysis(
        threat_id=threat.id, user_id=user.id, kind=body.kind, card_id=draw_card()
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        # Lost the race — someone finished analysing this threat+kind first. The
        # UniqueConstraint(threat_id, kind) is doing exactly its job.
        await session.rollback()
        raise HTTPException(status_code=409, detail="Цю ціль уже проаналізовано") from None

    return AnalyzeOut(
        threat_id=row.threat_id,
        kind=row.kind,
        card_id=row.card_id,
        created_at=row.created_at,
    )


@gamification_router.get("/analysis/threat/{threat_id}", response_model=ThreatAnalysisStateOut)
async def threat_analysis_state(
    threat_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    rows = (
        await session.scalars(
            select(ThreatAnalysis).where(ThreatAnalysis.threat_id == threat_id)
        )
    ).all()
    state = ThreatAnalysisStateOut(track_taken=False, remains_taken=False)
    for r in rows:
        if r.kind == "track":
            state.track_taken = True
            if r.user_id == user.id:
                state.mine_track = r.card_id
        elif r.kind == "remains":
            state.remains_taken = True
            if r.user_id == user.id:
                state.mine_remains = r.card_id
    return state


@gamification_router.put("/me/gamification", response_model=GamificationPrefOut)
async def set_gamification_pref(
    body: GamificationPrefIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Persist the account-bound gamification toggle so it syncs across devices."""
    user.gamification = body.enabled
    await session.commit()
    return GamificationPrefOut(enabled=user.gamification)


async def _collection_for(session: AsyncSession, user_id: int) -> CollectionOut:
    rows = (
        await session.execute(
            select(
                ThreatAnalysis.card_id,
                func.count().label("count"),
                func.min(ThreatAnalysis.created_at).label("first_at"),
            )
            .where(ThreatAnalysis.user_id == user_id)
            .group_by(ThreatAnalysis.card_id)
            .order_by(ThreatAnalysis.card_id)
        )
    ).all()
    cards = [CardCountOut(card_id=r.card_id, count=r.count, first_at=r.first_at) for r in rows]
    return CollectionOut(
        cards=cards,
        total_analyses=sum(c.count for c in cards),
        card_count=CARD_COUNT,
    )


@gamification_router.get("/analysis/collection", response_model=CollectionOut)
async def my_collection(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    return await _collection_for(session, user.id)


@gamification_router.get("/collection/{user_id}", response_model=CollectionOut)
async def friend_collection(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Another user's collection — visible only to that user themselves or an
    accepted friend (collections aren't public)."""
    if user_id != user.id and not await are_friends(session, user.id, user_id):
        raise HTTPException(status_code=403, detail="Колекція доступна лише друзям")
    return await _collection_for(session, user_id)

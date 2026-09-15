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

from ...auth.deps import get_current_user
from ...db import get_session
from ...domain.cards import (
    CARD_COUNT,
    MILESTONE_CARDS,
    STALE_AFTER,
    draw_card,
    eligible_kind_for,
    milestones_owned,
)
from ...models import (
    CardAward,
    Threat,
    ThreatAnalysis,
    ThreatEvent,
    User,
    utcnow,
)
from ...schemas import (
    AnalyzeIn,
    AnalyzeOut,
    CardCountOut,
    CollectionOut,
    GamificationPrefIn,
    GamificationPrefOut,
    ThreatAnalysisStateOut,
)
from ...timeutil import within
from ..deps import are_friends

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
        milestones=await _grant_milestones(session, user.id),
    )


async def _grant_milestones(session: AsyncSession, user_id: int) -> list[int]:
    """Hand over every milestone card this account's analysis count has now
    reached but never received, ascending — what the reveal shows one by one
    after the drawn card.

    Usually empty, and at most one at a time going forward. It returns several
    only on the first analysis after a threshold moves, or after this feature
    shipped to an account that had already passed one: the catch-up is the whole
    reason the grant is a row rather than arithmetic over the count.
    """
    done = await session.scalar(
        select(func.count()).select_from(ThreatAnalysis).where(ThreatAnalysis.user_id == user_id)
    )
    owed = set(milestones_owned(done)) - await _awarded_ids(session, user_id)
    if not owed:
        return []

    granted = []
    for card_id in sorted(owed, key=lambda c: MILESTONE_CARDS[c]):
        try:
            # A SAVEPOINT per insert: a concurrent analysis on another device can
            # only lose this unique constraint, and losing it must not take the
            # rest of the grant (or the analysis just committed) down with it.
            async with session.begin_nested():
                session.add(CardAward(user_id=user_id, card_id=card_id))
            granted.append(card_id)
        except IntegrityError:
            pass  # already awarded by that other analysis — not ours to reveal
    await session.commit()
    return granted


async def _awarded_ids(session: AsyncSession, user_id: int) -> set[int]:
    rows = await session.scalars(
        select(CardAward.card_id).where(CardAward.user_id == user_id)
    )
    return set(rows)


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
    # At most two rows (one per ANALYSIS_KIND), so naming their authors is one
    # small IN query rather than a join on every poll of this endpoint.
    others = {r.user_id for r in rows if r.user_id != user.id}
    names: dict[int, str | None] = {}
    if others:
        found = await session.execute(
            select(User.id, User.display_name).where(User.id.in_(others))
        )
        names = dict(found.all())
    state = ThreatAnalysisStateOut(track_taken=False, remains_taken=False)
    for r in rows:
        if r.kind == "track":
            state.track_taken = True
            if r.user_id == user.id:
                state.mine_track = r.card_id
            else:
                state.track_by = names.get(r.user_id)
        elif r.kind == "remains":
            state.remains_taken = True
            if r.user_id == user.id:
                state.mine_remains = r.card_id
            else:
                state.remains_by = names.get(r.user_id)
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
    # Every row above IS one analysis, so the copies sum is the analysis count.
    done = sum(c.count for c in cards)
    # Milestone cards come from the award ledger, NOT from `done` — one this
    # account has earned but not yet been handed stays out of the collection
    # until the analysis that reveals it (see _grant_milestones).
    awards = await session.scalars(
        select(CardAward).where(CardAward.user_id == user_id).order_by(CardAward.card_id)
    )
    cards += [CardCountOut(card_id=a.card_id, count=1, first_at=a.created_at) for a in awards]
    return CollectionOut(cards=cards, total_analyses=done, card_count=CARD_COUNT)


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

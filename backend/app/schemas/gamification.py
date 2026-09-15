"""Collectible-card analysis: requests, verdicts and the collection view."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator

from ..models import AnalysisKind
from .base import _as_utc


class AnalyzeIn(BaseModel):
    """POST /analysis — analyse a target for a card."""

    threat_id: int
    kind: AnalysisKind


class AnalyzeOut(BaseModel):
    """A successful analysis: the card that dropped, plus any milestone cards
    this analysis just unlocked (see domain/cards.MILESTONE_CARDS) — usually
    empty, and shown after the drawn card in the reveal."""

    threat_id: int
    kind: AnalysisKind
    card_id: int
    created_at: datetime
    milestones: list[int] = []

    _tz = field_validator("created_at", mode="before")(_as_utc)


class ThreatAnalysisStateOut(BaseModel):
    """GET /analysis/threat/{id} — which analyses this target has left, which
    (if any) the current user already claimed, and who took the ones they
    didn't. Drives the inspect-badge button: `*_taken` disables it globally,
    `mine_*` shows the card the user won, `*_by` names the analyst otherwise.

    `*_by` is the analyst's DISPLAY NAME and nothing else — never their email or
    id. The claim is first-writer-wins and global, so "someone else got here
    first" is already public; who that was is the part worth showing, and an
    address is not part of it. Null when they never set a name, in which case
    the UI says only that the slot is taken (the honest answer — inventing
    «Анонім» would read like a real handle).
    """

    track_taken: bool
    remains_taken: bool
    mine_track: int | None = None  # card_id the current user got, or null
    mine_remains: int | None = None
    track_by: str | None = None
    remains_by: str | None = None


class CardCountOut(BaseModel):
    """One collected card + how many copies the user has. A milestone card is
    always a single copy, earned at the analysis that crossed its threshold."""

    card_id: int
    count: int
    first_at: datetime

    _tz = field_validator("first_at", mode="before")(_as_utc)


class CollectionOut(BaseModel):
    """GET /analysis/collection — the current user's whole card collection."""

    cards: list[CardCountOut] = []
    total_analyses: int  # real analyses only — milestone cards are not analyses
    card_count: int  # size of the full deck, so the UI can show "collected N of M"


class GamificationPrefIn(BaseModel):
    """PUT /me/gamification — flip the account-bound gamification toggle."""

    enabled: bool


class GamificationPrefOut(BaseModel):
    enabled: bool

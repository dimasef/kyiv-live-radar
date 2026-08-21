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
    """A successful analysis: the card that dropped."""

    threat_id: int
    kind: AnalysisKind
    card_id: int
    created_at: datetime

    _tz = field_validator("created_at", mode="before")(_as_utc)


class ThreatAnalysisStateOut(BaseModel):
    """GET /analysis/threat/{id} — which analyses this target has left, and which
    (if any) the current user already claimed. Drives the inspect-badge button:
    `*_taken` disables it globally, `mine.*` shows the card the user won."""

    track_taken: bool
    remains_taken: bool
    mine_track: int | None = None  # card_id the current user got, or null
    mine_remains: int | None = None


class CardCountOut(BaseModel):
    """One collected card + how many copies the user has."""

    card_id: int
    count: int
    first_at: datetime

    _tz = field_validator("first_at", mode="before")(_as_utc)


class CollectionOut(BaseModel):
    """GET /analysis/collection — the current user's whole card collection."""

    cards: list[CardCountOut] = []
    total_analyses: int
    card_count: int  # size of the full deck, so the UI can show "collected N of M"


class GamificationPrefIn(BaseModel):
    """PUT /me/gamification — flip the account-bound gamification toggle."""

    enabled: bool


class GamificationPrefOut(BaseModel):
    enabled: bool

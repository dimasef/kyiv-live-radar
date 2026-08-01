"""Threat tracks, their sightings, and the feed entries built from them."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from ..models import ClosedReason, DecisionSource, TargetType, ThreatKind, ThreatScope, ThreatStatus
from .base import _as_utc


class ThreatEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    threat_id: int
    district_id: int
    raw_text: str
    event_time: datetime
    confidence: float
    decision_source: DecisionSource
    translated_text: str | None = None
    # Multi-source attribution.
    source_id: int | None = None
    source_name: str | None = None
    # Original channel message id — exposed so the frontend can detect several
    # events that came from ONE message (e.g. a "дорозвідка" closing several
    # tracks at once) and display them as one grouped feed card.
    source_message_id: int | None = None
    forwarded_from_id: int | None = None
    event_target_type: TargetType | None = None
    # Group size known as of this event (running-max at the time). The feed shows
    # this instead of the track's final count; NULL for pre-column events.
    event_target_count: int | None = None
    # Operator-facing gist from the LLM triage verdict (<=80 chars) — the feed
    # uses it as the card headline, raw_text collapsed beneath. NULL for
    # rule-only events (the feed falls back to raw_text).
    llm_summary: str | None = None
    # Denormalized point for convenient map rendering.
    lat: float | None = None
    lon: float | None = None

    _tz_event_time = field_validator("event_time", mode="before")(_as_utc)


class ThreatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    target_type: TargetType
    status: ThreatStatus
    # 'track' | 'impact' — see app/lifecycle.py. Optional/defaulted so this
    # stays byte-compatible with clients built before the field existed.
    kind: ThreatKind = "track"
    # Explicit reason the track closed (destroyed/all_clear/stand_down/stale);
    # NULL while open. Optional for the same reason as `kind`.
    closed_reason: ClosedReason | None = None
    scope: ThreatScope = "district"
    incident_id: int | None = None
    target_count: int = 1
    closed_at: datetime | None = None
    # Derived multi-source fusion signals.
    corroboration_count: int = 1
    has_conflict: bool = False
    confidence: float = 0.5
    events: list[ThreatEventOut] = []

    _tz_created_at = field_validator("created_at", "closed_at", mode="before")(_as_utc)


class FeedEntryOut(BaseModel):
    """One event feed row: the sighting plus its track's current derived state,
    for the frontend event log to hydrate on page load (see /events/recent)."""

    event: ThreatEventOut
    threat: ThreatOut

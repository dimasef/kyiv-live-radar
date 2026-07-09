from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class DistrictOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name_uk: str
    name_en: str
    lat: float
    lon: float
    aliases: list[str] = []


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_key: str
    name: str
    trust_weight: float


class ThreatEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    threat_id: int
    district_id: int
    raw_text: str
    event_time: datetime
    confidence: float
    decision_source: str
    translated_text: Optional[str] = None
    # Multi-source attribution.
    source_id: Optional[int] = None
    source_name: Optional[str] = None
    forwarded_from_id: Optional[int] = None
    event_target_type: Optional[str] = None
    # Denormalized point for convenient map rendering.
    lat: Optional[float] = None
    lon: Optional[float] = None


class ThreatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    target_type: str
    status: str
    target_count: int = 1
    closed_at: Optional[datetime] = None
    # Derived multi-source fusion signals.
    corroboration_count: int = 1
    has_conflict: bool = False
    confidence: float = 0.5
    events: list[ThreatEventOut] = []


class FeedEntryOut(BaseModel):
    """One event feed row: the sighting plus its track's current derived state,
    for the frontend event log to hydrate on page load (see /events/recent)."""

    event: ThreatEventOut
    threat: ThreatOut


class WSMessage(BaseModel):
    """Envelope broadcast over the WebSocket."""

    type: str  # 'event' | 'status' | 'hello'
    threat: Optional[ThreatOut] = None
    event: Optional[ThreatEventOut] = None

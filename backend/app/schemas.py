from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


def _as_utc(v: object) -> object:
    """SQLite drops tzinfo on round-trip even with DateTime(timezone=True) —
    every stored datetime is UTC wall-clock, just naive by the time it gets
    here. Reattach UTC before serialization so API responses carry an
    explicit offset ('Z'/'+00:00') instead of an ambiguous naive string the
    frontend would otherwise misinterpret as browser-local time."""
    if isinstance(v, datetime) and v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v


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
    # Original channel message id — exposed so the frontend can detect several
    # events that came from ONE message (e.g. a "дорозвідка" closing several
    # tracks at once) and display them as one grouped feed card.
    source_message_id: Optional[int] = None
    forwarded_from_id: Optional[int] = None
    event_target_type: Optional[str] = None
    # Group size known as of this event (running-max at the time). The feed shows
    # this instead of the track's final count; NULL for pre-column events.
    event_target_count: Optional[int] = None
    # Denormalized point for convenient map rendering.
    lat: Optional[float] = None
    lon: Optional[float] = None

    _tz_event_time = field_validator("event_time", mode="before")(_as_utc)


class ThreatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    target_type: str
    status: str
    # 'track' | 'impact' — see app/lifecycle.py. Optional/defaulted so this
    # stays byte-compatible with clients built before the field existed.
    kind: str = "track"
    # Explicit reason the track closed (destroyed/all_clear/stand_down/stale);
    # NULL while open. Optional for the same reason as `kind`.
    closed_reason: Optional[str] = None
    scope: str = "district"
    incident_id: Optional[int] = None
    target_count: int = 1
    closed_at: Optional[datetime] = None
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


class IncidentOut(BaseModel):
    """A coordinated attack with counts aggregated from its member threats."""

    id: int
    started_at: datetime
    ended_at: Optional[datetime] = None
    target_type: str
    status: str  # 'active' | 'ended'
    # Aggregates over member threats (computed in serialize.py::incident_out).
    track_count: int = 0        # inbound tracks (excludes impacts and city alerts)
    impact_count: int = 0       # distinct confirmed strike locations
    citywide: bool = False      # a city-wide alert is part of this attack
    district_count: int = 0     # distinct raions touched (excludes the sentinel)
    # --- Attack classification (derived — see app/attack.py::classify) ---
    classification: str = "unknown"  # 'drone'|'cruise_missile'|'ballistic'|'combined'|'unknown'
    attack_types: list[str] = []
    alert_id: Optional[int] = None
    decoy_suspected: bool = False
    has_hypersonic: bool = False
    # Single source of truth for "worth a prominent banner" — ported from the
    # frontend's former IncidentBanner.tsx::isNotable so the client just reads
    # this instead of recomputing it.
    notable: bool = False

    _tz_incident = field_validator("started_at", "ended_at", mode="before")(_as_utc)


class NoticeOut(BaseModel):
    """A non-threat feed notice (all-clear / attack summary) for the event log."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str  # 'clear' | 'summary'
    text: str
    target_type: str
    event_time: datetime
    source_id: Optional[int] = None
    source_name: Optional[str] = None

    _tz_notice = field_validator("event_time", mode="before")(_as_utc)


class AlertOut(BaseModel):
    """An official air-raid alert window (тривога -> відбій)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    scope: str  # 'city' | 'oblast'
    alert_type: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    provider: str
    closed_reason: Optional[str] = None  # 'official' | 'failsafe'; None while open

    _tz_alert = field_validator("started_at", "ended_at", mode="before")(_as_utc)


class WSMessage(BaseModel):
    """Envelope broadcast over the WebSocket."""

    type: str  # 'event' | 'status' | 'notice' | 'alert' | 'attack' | 'health' | 'hello'
    threat: Optional[ThreatOut] = None
    event: Optional[ThreatEventOut] = None
    notice: Optional[NoticeOut] = None
    alert: Optional[AlertOut] = None
    incident: Optional[IncidentOut] = None
    # 'health' frame payload: whether the live Telegram feed looks healthy —
    # see telegram_listener.py::feed_health.
    feed_ok: Optional[bool] = None

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
    # Operator-facing gist from the LLM triage verdict (<=80 chars) — the feed
    # uses it as the card headline, raw_text collapsed beneath. NULL for
    # rule-only events (the feed falls back to raw_text).
    llm_summary: Optional[str] = None
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
    # Distinct raion ids touched by member events (excludes the sentinel) — the
    # frontend highlights these polygons on the map for an active incident.
    district_ids: list[int] = []
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
    kind: str  # 'clear' | 'summary' | 'directional' | 'forecast' | 'status'
    text: str
    target_type: str
    event_time: datetime
    source_id: Optional[int] = None
    source_name: Optional[str] = None
    # Curated origin key for a directional notice (else None) + who produced it
    # ('rule'|'llm'). LLM notices render with an "AI · неперевірено" badge.
    origin: Optional[str] = None
    generated_by: str = "rule"

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


class AxisOut(BaseModel):
    """A directional threat axis for the map's screen-edge wedge layer. Bearing
    and origin display name are derived server-side from the curated origins
    table (app/domain/origins.py) — the client just draws the wedge."""

    id: int
    sector: str            # compass octant
    bearing_deg: int       # 0=N, 90=E — the wedge direction
    origin_key: Optional[str] = None
    origin_name: Optional[str] = None  # display label ("Брянщина"); None for bare-sector
    target_type: str
    status: str            # 'unverified' | 'corroborated' | 'expired'
    corroboration_count: int = 1
    created_at: datetime
    last_seen_at: datetime
    expires_at: Optional[datetime] = None

    _tz_axis = field_validator("created_at", "last_seen_at", "expires_at", mode="before")(_as_utc)


class RawEventLinkOut(BaseModel):
    """One ThreatEvent a raw message produced — the same T{threat_id}/
    M{event_id} pair shown as a dev badge in the feed. A single raw message
    can produce SEVERAL (e.g. an untyped "дорозвідка" closing multiple open
    tracks at once), hence a list on RawMessageOut rather than one pair."""

    threat_id: int
    event_id: int


class RawMessageOut(BaseModel):
    """One verbatim ingested message plus a debug diagnosis of what the
    pipeline did with it — see GET /raw_messages. `outcome`/`events`/
    `notice_id` are authoritative when a real ThreatEvent/Notice matched
    ('подія'/'нотіс'); a best-effort re-derived label otherwise (see
    api/raw_diagnosis.py)."""

    id: int
    source_id: Optional[int] = None
    source_name: Optional[str] = None
    message_id: Optional[int] = None
    text: str
    event_time: datetime
    forwarded_from_id: Optional[int] = None
    reply_to_message_id: Optional[int] = None
    processed: bool
    outcome: str
    events: list[RawEventLinkOut] = []
    notice_id: Optional[int] = None
    # Whether the LLM fallback was called for this message — None for rows
    # ingested before this was tracked (genuinely unknown, not "no").
    llm_attempted: Optional[bool] = None
    # Token usage/cost for that call — set together with llm_attempted=True
    # whenever it actually completed; None otherwise.
    llm_input_tokens: Optional[int] = None
    llm_output_tokens: Optional[int] = None
    llm_cost_usd: Optional[float] = None
    # The full structured LLM response (district_ids + triage category/surface/
    # summary) — present only when the LLM produced usable JSON; None otherwise.
    # Collected for /raw audit; nothing in the product routes on it yet.
    llm_response: Optional[dict] = None
    # Async-triage bookkeeping (see TRIAGE_STATES/TRIAGE_ACTIONS) — where the
    # message went in the triage queue and what routing did with its verdict.
    # NULL for messages the triage engine never enqueued.
    triage_state: Optional[str] = None
    triage_action: Optional[str] = None

    _tz_raw = field_validator("event_time", mode="before")(_as_utc)


class RawMessagesPage(BaseModel):
    """Cursor-paginated page of raw messages, newest first."""

    items: list[RawMessageOut]
    # Pass as `before_id` to fetch the next page; None once there's no more.
    next_before_id: Optional[int] = None


class RawSourceOut(BaseModel):
    """One monitored channel, for the /raw channel filter dropdown."""

    id: int
    name: str


class RawCountOut(BaseModel):
    """How many raw messages match the current /raw filter set."""

    count: int


class RawExportOut(BaseModel):
    """All raw messages matching the current filter (up to the export cap),
    for offline analysis — see GET /raw_messages/export. `truncated` flags a
    partial export so it's never mistaken for the complete set."""

    messages: list[RawMessageOut]
    truncated: bool


class RawLlmStatsOut(BaseModel):
    """Aggregate LLM fallback usage across all raw messages — see
    GET /raw_messages/llm_stats."""

    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


class WSMessage(BaseModel):
    """Envelope broadcast over the WebSocket."""

    # 'event'|'status'|'notice'|'alert'|'attack'|'axis'|'health'|'online'|'hello'
    type: str
    threat: Optional[ThreatOut] = None
    event: Optional[ThreatEventOut] = None
    notice: Optional[NoticeOut] = None
    alert: Optional[AlertOut] = None
    incident: Optional[IncidentOut] = None
    axis: Optional[AxisOut] = None
    # 'health' frame payload: whether the live Telegram feed looks healthy —
    # see telegram_listener.py::feed_health.
    feed_ok: Optional[bool] = None
    # 'online' frame payload: how many WS clients are currently connected.
    online: Optional[int] = None

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


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


class JournalAlertWindowOut(BaseModel):
    """One тривога→відбій window within a journal day. `seconds` stays 0 for an
    incomplete window (still open / failsafe-closed) so it can never be picked
    as the day's longest."""

    started_at: datetime
    ended_at: Optional[datetime] = None
    seconds: int = 0
    incomplete: bool = False

    _tz_window = field_validator("started_at", "ended_at", mode="before")(_as_utc)


class JournalDayOut(BaseModel):
    """One calendar day of aggregated threat activity — see GET /journal/days.
    Mirrors app/domain/journal.py::DayStat. The intensity score is derived on
    the client from these fields (the frontend owns the weighting)."""

    date: str  # Kyiv-local ISO date, YYYY-MM-DD
    attack_count: int = 0
    track_count: int = 0
    target_count: int = 0
    impact_count: int = 0
    # Per-target-type threat counts, keyed by TARGET_TYPES (shahed/jet_drone/
    # missile/ballistic/unknown) — feeds the day's type-breakdown bar.
    type_counts: dict[str, int] = {}
    alert_count: int = 0
    alert_seconds: int = 0
    longest_alert_seconds: int = 0
    # A day's alert duration is a lower bound when some alert was still open or
    # failsafe-closed (see ALERT_CLOSED_REASONS) — the UI prefixes "≥".
    alert_incomplete: bool = False
    # Chronological тривога→відбій intervals — the UI lists each one.
    alert_windows: list[JournalAlertWindowOut] = []
    # Most-active district first (by event count), so a "top districts" UI can
    # just take the head of the list.
    district_ids: list[int] = []
    district_count: int = 0


class JournalOut(BaseModel):
    """GET /journal/days — every day in [from_date, to_date] inclusive, with
    zero-activity days present (as empty stats) so the calendar renders gaps."""

    from_date: str
    to_date: str
    days: list[JournalDayOut]


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
    # Representative centroid of the origin region — the client morphs the edge
    # wedge into an on-map source marker here when it's zoomed out enough to see
    # this spot. None for bare-sector axes (a direction with no named place).
    origin_lat: Optional[float] = None
    origin_lon: Optional[float] = None
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
    # The target type stamped on this event ('shahed'|'ballistic'|... or
    # 'unknown'/None) — surfaced in /raw so an admin sees what type the message
    # was classified as, not just that it produced an event.
    target_type: Optional[str] = None


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


class PushKeysIn(BaseModel):
    """The browser PushSubscription's encryption keys."""

    p256dh: str
    auth: str


class BrowserSubscriptionIn(BaseModel):
    """PushSubscription.toJSON() from the browser."""

    endpoint: str
    keys: PushKeysIn


class HomeZoneIn(BaseModel):
    """The home zone this subscription wants guarded (mirrors the client's
    localStorage home — see frontend store/homeSlice.ts)."""

    lat: float
    lon: float
    radius_km: float = 3.0


class PushPrefsIn(BaseModel):
    """Notification preferences (phase 1). Defaults reproduce the pre-0.10
    behavior (warning floor, every type) plus the citywide push on."""

    min_level: Literal["warning", "danger"] = "warning"
    types: list[Literal["ballistic", "missile", "shahed", "jet_drone"]] = [
        "ballistic", "missile", "shahed", "jet_drone",
    ]
    citywide: bool = True


class PushSubscribeIn(BaseModel):
    """POST /push/subscribe body. Upsert by endpoint; re-POSTed on every home
    or prefs change so the server copy never goes stale."""

    subscription: BrowserSubscriptionIn
    home: Optional[HomeZoneIn] = None
    prefs: Optional[PushPrefsIn] = None


class PushUnsubscribeIn(BaseModel):
    endpoint: str


class PushConfigOut(BaseModel):
    """GET /push/config — whether push is configured server-side, and the VAPID
    public key the browser needs for pushManager.subscribe. Fetched at runtime
    so key rotation never requires a frontend rebuild."""

    enabled: bool
    public_key: Optional[str] = None


class RegisterIn(BaseModel):
    """POST /auth/register — email+password signup."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: Optional[str] = Field(default=None, max_length=120)


class LoginIn(BaseModel):
    """POST /auth/login."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshIn(BaseModel):
    """POST /auth/refresh — exchange a refresh token for a new access token."""

    refresh: str


class GoogleAuthIn(BaseModel):
    """POST /auth/google — the id_token from Google Identity Services."""

    credential: str


class TelegramAuthIn(BaseModel):
    """POST /auth/telegram — the Telegram Login Widget payload. extra='allow'
    so any future widget field is preserved for the HMAC data-check-string
    (which must include EXACTLY the fields Telegram signed)."""

    model_config = ConfigDict(extra="allow")

    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str


class UserOut(BaseModel):
    """The authenticated user's public profile."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: Optional[str] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    role: str
    # Which sign-in methods are linked: 'password' + any of PROVIDERS.
    providers: list[str] = []


class TokenPairOut(BaseModel):
    """Access + refresh tokens plus the user they belong to."""

    access: str
    refresh: str
    token_type: str = "bearer"
    user: UserOut


class AccessTokenOut(BaseModel):
    """POST /auth/refresh result — a fresh access token only."""

    access: str
    token_type: str = "bearer"


class WSMessage(BaseModel):
    """Envelope broadcast over the WebSocket."""

    # 'event'|'status'|'notice'|'alert'|'attack'|'axis'|'health'|'online'|'hello'|'ping'
    # 'ping' carries no payload — a bare heartbeat frame (see pipeline/keepalive.py).
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

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, get_args

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class District(Base):
    """Gazetteer entry: a Kyiv district/microdistrict with a representative point.

    NOTE: lat/lon is a single representative point (centroid), not a polygon.
    Bearing/vector math built on centroids is coarse — treat it as indicative
    only. Real district polygons (from OSM) are a later refinement.
    """

    __tablename__ = "districts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name_uk: Mapped[str] = mapped_column(String(120))
    name_en: Mapped[str] = mapped_column(String(120))
    # Known spelling variants / abbreviations used by spotters, e.g. "Троя" -> Троєщина.
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    city: Mapped[str] = mapped_column(String(80), default="Kyiv")
    # Real OSM boundary (GeoJSON Polygon/MultiPolygon geometry) for the 10
    # administrative raions; SQL NULL for microdistricts/approach towns (points
    # only). none_as_null keeps Python None as SQL NULL so IS NOT NULL filters work.
    boundary: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )


# Allowed enum-like values. Each is declared ONCE as a `Literal` and the runtime
# tuple is derived from it with `get_args` — never the other way round and never
# both by hand. That makes the two impossible to drift apart, and it is what puts
# a real union (not a bare `string`) into the OpenAPI schema, so the generated
# frontend types narrow these fields too.
TargetType = Literal["shahed", "jet_drone", "missile", "ballistic", "unknown"]
TARGET_TYPES: tuple[TargetType, ...] = get_args(TargetType)
# 'dismissed' = an admin manually cancelled a false-positive track (see
# app/domain/lifecycle.py::close_track with reason 'dismissed'). Closed like any
# other, but excluded from stats/journal so a parser mistake never counts as a
# real target — reversible via reopen_track.
ThreatStatus = Literal["unconfirmed", "tracking", "destroyed", "lost", "impact", "dismissed"]
THREAT_STATUSES: tuple[ThreatStatus, ...] = get_args(ThreatStatus)
# 'track' = an inbound target being followed; 'impact' = a closed-on-creation
# confirmed-strike marker. Split out of `status` (which conflates kind with
# lifecycle) — see app/lifecycle.py.
ThreatKind = Literal["track", "impact"]
THREAT_KINDS: tuple[ThreatKind, ...] = get_args(ThreatKind)
# A localized track over a raion, vs a city-wide "ціль на місто" that renders as
# a banner rather than a map point.
ThreatScope = Literal["district", "city"]
THREAT_SCOPES: tuple[ThreatScope, ...] = get_args(ThreatScope)
# Explicit reason a track closed, replacing `status='lost'`'s three overloaded
# meanings (відбій / дорозвідка stand-down / silence timeout). NULL while open.
ClosedReason = Literal["destroyed", "all_clear", "stand_down", "stale", "dismissed"]
CLOSED_REASONS: tuple[ClosedReason, ...] = get_args(ClosedReason)
# Where the structured event came from — critical for parser eval/debugging.
# 'triage' = an async second-pass LLM verdict RESCUED a message the sync rules
# path suppressed/couldn't localize (see app/pipeline/triage.py). Distinct from
# 'llm' (the inline sync fallback that runs while ingest holds the lock).
DecisionSource = Literal["rule", "llm", "sim", "triage"]
DECISION_SOURCES: tuple[DecisionSource, ...] = get_args(DecisionSource)
# Async-triage bookkeeping on a raw message (app/pipeline/triage.py). state =
# where the message is in the triage queue's lifecycle; action = what routing
# ultimately did with the verdict. Both NULL for messages never enqueued.
TRIAGE_STATES = ("pending", "done", "skipped", "budget", "error")
TRIAGE_ACTIONS = ("none", "suppress_confirmed", "notice", "axis", "rescue_candidate", "rescued", "late")
# A directional threat axis' lifecycle (app/domain/axes.py). 'unverified' = one
# source only; 'corroborated' = >= axis_min_sources independent sources agreed;
# 'expired' = timed out of the live layer by the sweeper.
AxisState = Literal["unverified", "corroborated", "expired"]
AXIS_STATES: tuple[AxisState, ...] = get_args(AxisState)
# Who produced a Notice — a deterministic rule handler or an LLM triage verdict
# (surfaced with an "AI · неперевірено" badge in the feed).
NoticeGenerator = Literal["rule", "llm"]
NOTICE_GENERATORS: tuple[NoticeGenerator, ...] = get_args(NoticeGenerator)
# What a Notice is about — an all-clear, a retrospective attack summary, or one
# of the three LLM-triage context notices.
NoticeKind = Literal["clear", "summary", "directional", "forecast", "status"]
NOTICE_KINDS: tuple[NoticeKind, ...] = get_args(NoticeKind)
# 'spotter' = volunteer sighting channel, parsed by parser.py into
# threats/tracks. 'alert' = official air-raid alert channel (@KyivCityOfficial
# today), parsed by alert_parser.py into Alert rows — routed separately so an
# official "Відбій…" never trips the spotter parser's all-clear and closes
# tracks prematurely (see telegram_listener.py).
SourceRole = Literal["spotter", "alert"]
SOURCE_ROLES: tuple[SourceRole, ...] = get_args(SourceRole)
AlertScope = Literal["city", "oblast"]
ALERT_SCOPES: tuple[AlertScope, ...] = get_args(AlertScope)
# 'official' = a real відбій from the alert channel; 'failsafe' = the sweeper
# force-closed an alert open past alert_failsafe_hours (dead Telethon session
# ate the відбій, not a real day-long siren) — see app/alerts.py.
AlertClosedReason = Literal["official", "failsafe", "dismissed"]
ALERT_CLOSED_REASONS: tuple[AlertClosedReason, ...] = get_args(AlertClosedReason)
# Why an Incident (attack) ended: a spotter's "Відбій" ('all_clear'), the
# official city alert ending ('alert_end'), or the stale sweeper timing it out
# ('stale'). NULL while active — see app/incidents.py.
IncidentEndedReason = Literal["all_clear", "alert_end", "stale", "dismissed"]
INCIDENT_ENDED_REASONS: tuple[IncidentEndedReason, ...] = get_args(IncidentEndedReason)
# User roles (app/auth/). 'admin' and 'admin_g' both get the service tools
# (/raw, source management — see require_admin); 'user' gets personalization
# only. 'admin' is derived from the env allowlists on every login; 'admin_g' is
# a manual DB-only role that role resolution preserves (never auto-assigned,
# never overwritten — see auth/service.resolve_and_set_role).
UserRole = Literal["admin", "admin_g", "user"]
USER_ROLES: tuple[UserRole, ...] = get_args(UserRole)
ADMIN_ROLES: tuple[UserRole, ...] = ("admin", "admin_g")
# Linked SSO providers on OAuthIdentity. Email+password is native on the User
# row (password_hash), NOT an identity — so it's absent here.
PROVIDERS = ("google", "telegram")
# Admin corrections harvested from the /admin console into a labeled regression
# dataset (app/domain/corrections.py). 'false_positive' = a dismissed track's
# message shouldn't have localized; 'retype' = wrong target_type; 'relocate' =
# wrong district. `origin` records which admin action produced it.
CorrectionKind = Literal["false_positive", "retype", "relocate"]
CORRECTION_KINDS: tuple[CorrectionKind, ...] = get_args(CorrectionKind)
CORRECTION_ORIGINS = ("dismiss", "retype_threat", "move_event")
# Toponym candidates captured from the coverage-gap queue — NOT live gazetteer
# edits (those stay a code-review step with a stem-collision sweep, see
# CLAUDE.md). 'added' = a human later promoted it into app/gazetteer.py.
GazCandidateStatus = Literal["pending", "geocoded", "added", "rejected"]
GAZ_CANDIDATE_STATUSES: tuple[GazCandidateStatus, ...] = get_args(GazCandidateStatus)
# User-filed bug reports (app/api/public/bugs.py -> the admin console tab).
BugReportStatus = Literal["new", "in_progress", "closed"]
BUG_REPORT_STATUSES: tuple[BugReportStatus, ...] = get_args(BugReportStatus)


class Source(Base):
    """A monitored Telegram channel (or other feed) that reports sightings.

    Multi-source fusion cross-validates reports across sources. `trust_weight`
    lets known-reliable channels count for more; aggregator/repost channels get
    a low weight so echoing the same original doesn't inflate confidence.

    The live Telethon listener subscribes to exactly the rows with
    `is_active=True` (managed from the /admin console) — the DB, not the env
    channel lists, is the source of truth for what's watched. `subscribe_ref`
    is the raw handle/id/invite-link the listener resolves each channel by;
    NULL falls back to `channel_key` (legacy rows, where for a public channel
    channel_key == username).
    """

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_key: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    trust_weight: Mapped[float] = mapped_column(Float, default=1.0)
    is_active: Mapped[bool] = mapped_column(default=True)
    # 'spotter' | 'alert' — see SOURCE_ROLES. Determines which parser/ingest
    # path a channel's messages go through.
    role: Mapped[str] = mapped_column(String(10), default="spotter")
    # Raw string the listener resolves this channel by (username without @, a
    # numeric id, or a t.me/+ invite link). NULL -> resolve by channel_key.
    subscribe_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # The channel's Telegram id, learned on the first successful resolve and
    # then treated as this row's true identity. A username is MUTABLE: a channel
    # can rename itself (@KievRadar -> @kyiv_allerts on 2026-08-03), and the
    # freed handle can be claimed by anyone — at which point resolving by handle
    # would silently subscribe us to a stranger's channel and feed its posts in
    # as a trusted spotter. The listener refuses any channel whose resolved id
    # doesn't match this one. BigInteger: Telegram ids are 64-bit.
    tg_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Last resolve/join error the listener hit for this channel, surfaced in the
    # admin UI so a mistyped handle is visible; cleared to NULL on a good connect.
    last_listener_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=utcnow
    )
    added_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class Alert(Base):
    """An official air-raid alert window (тривога -> відбій) from an
    authoritative source (Telegram @KyivCityOfficial today; alerts.in.ua /
    UkraineAlarm later — see `provider`). Independent of Incident: a "silent"
    alert with zero attacks is naturally representable (alert open, zero
    incidents) — linking the two is Phase 3.
    """

    __tablename__ = "alerts"
    # Alerts are always narrowed to a scope first, then ordered by start time.
    __table_args__ = (Index("ix_alerts_scope_started_at", "scope", "started_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(10))  # 'city' | 'oblast'
    alert_type: Mapped[str] = mapped_column(String(20), default="air_raid")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(20), default="telegram")
    # Provenance — which raw message started/ended this alert, for reprocess.
    started_raw_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_messages.id"), nullable=True
    )
    ended_raw_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_messages.id"), nullable=True
    )
    # 'official' | 'failsafe' (see ALERT_CLOSED_REASONS); NULL while open.
    closed_reason: Mapped[str | None] = mapped_column(String(20), nullable=True)


class RawMessage(Base):
    """Every incoming channel message, stored verbatim BEFORE parsing.

    First-hand data: kept in the source language, used to build parser eval sets
    and to reprocess history when the parser improves. `processed` marks whether
    the parser has already turned it into structured events.
    """

    __tablename__ = "raw_messages"
    # A real Telegram message_id is unique per channel — the same (source,
    # message_id) landing twice means a repeated backfill re-ingested it (SQLite
    # treats NULL != NULL, so simulator rows with no message_id are unaffected).
    __table_args__ = (UniqueConstraint("source_id", "message_id", name="uq_raw_message_source_msgid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("sources.id"), nullable=True
    )
    source: Mapped[Source | None] = relationship()
    # Telegram id. BigInteger: Telegram peer/message ids are 64-bit and channel
    # ids (e.g. -1001754665396) overflow Postgres INTEGER (int32). SQLite stores
    # INTEGER as 64-bit so this only ever bit on prod Postgres.
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    text: Mapped[str] = mapped_column(Text, default="")
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    # When WE stored it, as opposed to when Telegram says it was posted. Equal
    # to `event_time` within a second on the live path; far behind it whenever a
    # reconnect backfill replays history — which is exactly when tracks split
    # and phantom incidents appear (see migration 0022). NULL for rows stored
    # before this column existed: genuinely unknown, not backfillable.
    ingested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=True
    )
    forwarded_from_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # The ORIGIN channel's Telegram peer id, when this message is a repost —
    # `forwarded_from_id` alone is a message id, not globally unique across
    # channels; this disambiguates two different channels whose reposted
    # messages happen to share a numeric id. See fusion.py::_origin_keys.
    forwarded_from_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Telegram id of the message this one replies to (same channel). Channels like
    # «Місто Кия | Безпека» reply to the previous post about the SAME target, so the
    # reply chain identifies the track far better than time-proximity does.
    reply_to_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    processed: Mapped[bool] = mapped_column(default=False)
    # Whether the LLM fallback (parsing/llm.py) was actually CALLED for this
    # message — distinct from a ThreatEvent's decision_source=='llm' (which
    # also requires the call to have recovered a district; a call that found
    # nothing still spent the API budget). NULL for messages ingested before
    # this column existed — genuinely unknown, not backfillable (unlike
    # Notice.source_message_id, re-deriving this from today's parser/rules
    # would reflect current logic, not what actually ran historically).
    # Indexed: True on only ~5% of rows, and the /raw LLM filter selects on it.
    llm_attempted: Mapped[bool | None] = mapped_column(nullable=True, index=True)
    # Token usage/cost for that call — set together with llm_attempted=True
    # whenever the API actually responded (see parsing/llm.py::llm_extract).
    # NULL when llm_attempted is False/NULL, or when the call never completed
    # (timeout/network/API error — nothing was billed).
    llm_input_tokens: Mapped[int | None] = mapped_column(nullable=True)
    llm_output_tokens: Mapped[int | None] = mapped_column(nullable=True)
    llm_cost_usd: Mapped[float | None] = mapped_column(nullable=True)
    # The full structured response the LLM fallback returned — district_ids plus
    # the triage fields (category/surface/summary/target_type/status/...). Stored
    # verbatim so LLM calls are auditable on /raw and so the Stage-3 context
    # layer can be tuned against real responses. NULL when the LLM wasn't called
    # or the call produced no usable JSON. COLLECTED-ONLY: nothing in the live
    # pipeline routes on the triage fields yet (see parsing/llm.py::llm_extract).
    llm_response: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    # Async LLM triage bookkeeping (see TRIAGE_STATES/TRIAGE_ACTIONS and
    # app/pipeline/triage.py). NULL for messages the triage engine never
    # enqueued (rules already localized them, or they were pure junk).
    triage_state: Mapped[str | None] = mapped_column(String(12), nullable=True)
    triage_action: Mapped[str | None] = mapped_column(String(20), nullable=True)


class ThreatAxis(Base):
    """A directional threat axis — an inbound bearing/origin ("балістика з
    Брянщини") a spotter callout named without any Kyiv raion to localize. It is
    NOT a map point: the frontend draws it as a screen-edge wedge along the
    origin's compass bearing (app/domain/origins.py). Modelled as its own entity
    (not a Notice) because it has a lifecycle — a fusion window that absorbs
    repeat callouts, an unverified->corroborated promotion at
    axis_min_sources, and a TTL the sweeper expires it on — exactly the
    Alert/Incident pattern.
    """

    __tablename__ = "threat_axes"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # NULL while active; set when the sweeper expires the axis (TTL lapsed).
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    target_type: Mapped[str] = mapped_column(String(20), default="unknown")
    # Curated origin key (origins.ORIGIN_KEYS) when a toponym was named, else NULL
    # (a bare directional "курсом з півночі" carries only a sector).
    origin_key: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sector: Mapped[str] = mapped_column(String(4), default="N")  # compass octant
    status: Mapped[str] = mapped_column(String(12), default="unverified")
    corroboration_count: Mapped[int] = mapped_column(default=1)
    # Distinct source-origin dedup keys seen (same _origin_key idea as fusion.py)
    # so a channel reposting its own callout doesn't inflate corroboration.
    origin_keys_seen: Mapped[list] = mapped_column(JSON, default=list)
    # Provenance: the raw_message ids that fed this axis, for reprocess/audit.
    raw_ids: Mapped[list] = mapped_column(JSON, default=list)


class Notice(Base):
    """A non-threat feed notice — an all-clear ("відбій") or a retrospective
    attack summary ("8 балістичних С-400 по Києву"). These are important for the
    operator to SEE in the event log but are NOT live targets on the map, so they
    live outside the threat/track model and surface only in the feed timeline.
    """

    __tablename__ = "notices"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    # 'clear' | 'summary' (rule-emitted) | 'directional' | 'forecast' | 'status'
    # (LLM-triage-emitted context notices — see app/pipeline/triage.py).
    kind: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text, default="")
    target_type: Mapped[str] = mapped_column(String(20), default="unknown")
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("sources.id"), nullable=True, index=True
    )
    source: Mapped[Source | None] = relationship()
    # Original channel message id that produced this notice — same purpose as
    # ThreatEvent.source_message_id, so /raw_messages can trace a raw message
    # to the notice it became (NULL for notices created before this existed).
    source_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Curated origin key (origins.ORIGIN_KEYS) for a directional notice — the
    # feed clusters same-origin callouts and can point to the matching axis. NULL
    # for non-directional notices.
    origin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # 'rule' | 'llm' (see NOTICE_GENERATORS) — LLM-generated notices are shown as
    # unverified/AI in the feed. Defaults 'rule' so every historical notice reads
    # as authoritative, which they were.
    generated_by: Mapped[str] = mapped_column(String(10), default="rule")


class Incident(Base):
    """A coordinated attack — the umbrella grouping every track, impact and
    city-wide alert that belongs to ONE alert window ("one alert = one
    incident"). Its aggregate counts (targets / impacts / districts) are derived
    from its member threats at serialization time, not stored here.
    """

    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    # Time of the most recent member activity — a new threat joins this incident
    # only while this is fresh; the stale sweeper ends the incident once it lapses.
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # NULL while the attack is ongoing; set on all-clear or by the stale sweeper.
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    # Explicit reason the attack ended (see INCIDENT_ENDED_REASONS); NULL while
    # active, and NULL for historical incidents that ended before this field
    # existed (not backfilled — the real reason isn't recoverable from stored
    # data, unlike Threat.closed_reason's status-derived backfill in Phase 1).
    ended_reason: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Most severe target type among members (ballistic > missile > jet > shahed).
    target_type: Mapped[str] = mapped_column(String(20), default="unknown")
    # Accumulated SET of non-'unknown' member target_types (see
    # app/attack.py::classify, which derives the family/combined label from
    # this at serialization time — never stored itself).
    attack_types: Mapped[list] = mapped_column(JSON, default=list)
    # The official alert (see models.Alert) this attack belongs to, if any —
    # linked either forward (a new incident joins an already-open city alert)
    # or retroactively (a ballistic incident often starts before the siren;
    # app/alerts.py adopts it once the alert fires). NULL = no alert observed
    # for this attack (alert channel not configured, or a genuinely silent/
    # unannounced incident).
    alert_id: Mapped[int | None] = mapped_column(
        ForeignKey("alerts.id"), nullable=True, index=True
    )
    # How many member messages used decoy/EW vocabulary (see parser.py
    # ParseResult.decoy) — a modifier count, not a replacement classification;
    # an attack can be combined AND partially imitation.
    decoy_mentions: Mapped[int] = mapped_column(default=0)
    # Any member message named a hypersonic system (Кинджал/Циркон/aeroballistic)
    # — a flag on the attack, not a 6th target_type (see parser.py ParseResult.hypersonic).
    has_hypersonic: Mapped[bool] = mapped_column(default=False)

    threats: Mapped[list[Threat]] = relationship(back_populates="incident")


class Threat(Base):
    """A single target's track, from first sighting to destroyed/lost.

    Fusion fields (corroboration_count / has_conflict / confidence) are derived
    from the track's events across sources — see fusion.py.
    """

    __tablename__ = "threats"
    # /threats/active filters open tracks AND excludes admin-dismissed ones in
    # the same query, so one composite serves both — and its leading column
    # serves the plain closed_at lookups too.
    __table_args__ = (Index("ix_threats_closed_at_reason", "closed_at", "closed_reason"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    # The attack this track belongs to (Stage E grouping); NULL for pre-incident
    # data or a track not yet attached.
    incident_id: Mapped[int | None] = mapped_column(
        ForeignKey("incidents.id"), nullable=True, index=True
    )
    target_type: Mapped[str] = mapped_column(String(20), default="unknown")
    status: Mapped[str] = mapped_column(String(20), default="unconfirmed")
    # 'track' (still being followed) or 'impact' (closed-on-creation confirmed
    # strike). Kept alongside `status` rather than replacing it (see
    # THREAT_KINDS) — status still carries destroyed/lost/tracking/unconfirmed
    # for backwards-compat with existing serializer/frontend consumers.
    kind: Mapped[str] = mapped_column(String(10), default="track")
    # 'district' (a normal localized track) or 'city' (a city-wide threat with
    # no raion — "ціль на місто"). City-wide threats render as a banner, not a
    # map point; see the CITYWIDE_NAME_EN sentinel district their events attach to.
    scope: Mapped[str] = mapped_column(String(10), default="district")
    # Stated size of the group flying together ("2х" -> 2, "їх вже 3х" -> 3);
    # grows within the reply-chain as spotters revise it. 1 when unstated.
    target_count: Mapped[int] = mapped_column(default=1)
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Explicit reason the track closed (see CLOSED_REASONS) — NULL while open.
    # Replaces status='lost' overloading відбій/дорозвідка/silence-timeout
    # into one meaning; set only via app.domain.lifecycle.close_track().
    closed_reason: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # --- Derived multi-source fusion signals ---
    corroboration_count: Mapped[int] = mapped_column(default=1)  # distinct independent sources
    has_conflict: Mapped[bool] = mapped_column(default=False)    # sources disagree
    confidence: Mapped[float] = mapped_column(Float, default=0.5)  # fused 0..1

    incident: Mapped[Incident | None] = relationship(back_populates="threats")

    events: Mapped[list[ThreatEvent]] = relationship(
        back_populates="threat",
        order_by="ThreatEvent.event_time",
        cascade="all, delete-orphan",
    )


class User(Base):
    """A registered person (single-user MVP → now multi-user with roles).

    The public map stays open to everyone; a User row only exists once someone
    signs in. `email`/`password_hash` are both nullable so a Telegram-only or
    Google-only account (no local password, maybe no email) is representable.
    `role` is re-resolved from the env allowlist on every login and persisted so
    `require_admin` is a single cheap column read (see app/auth/service.py).
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Unique when present; NULL for a Telegram account with no email (SQLite &
    # Postgres both treat multiple NULLs as distinct, so many null-email rows coexist).
    email: Mapped[str | None] = mapped_column(String(320), unique=True, nullable=True)
    # True only when the provider vouched for the email (Google id_token). A
    # self-registered password account stays False — and an unverified email can
    # never resolve to admin (closes the "register as admin@… and self-promote" hole).
    email_verified: Mapped[bool] = mapped_column(default=False)
    # argon2 hash; NULL for OAuth/Telegram-only accounts (no local password).
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(10), default="user")
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    # Home location as a first-class user attribute (distinct from the per-device
    # PushSubscription copy) so it can be shared with friends independently of any
    # push subscription. Radius is NOT stored — friends see a marker only, and the
    # owner's radius stays client-side/push. `share_home` gates all friend
    # visibility: friendship alone never reveals a home.
    home_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    home_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    # The owner's danger-zone radius. Stored here (not just in localStorage and
    # the per-device push subscription) so a home survives opening the app on
    # another device — the account is the source of truth, the client copy is a
    # cache. Never leaves the server for anyone but the owner: friends get a
    # marker, and how far you consider "near home" is not theirs to know.
    home_radius_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    share_home: Mapped[bool] = mapped_column(default=False)
    # How the OWNER's own home marker looks on their map — an id from the
    # frontend's marker set plus a hex colour, NULL meaning "the default cyan
    # house". Private like contact_prefs below: friends still label the marker
    # themselves, so this never leaves the owner (absent from FriendOut).
    home_icon: Mapped[str | None] = mapped_column(String(32), nullable=True)
    home_color: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Whether that marker carries its coloured halo. NULL reads as "on", which
    # is what every marker looked like before the halo was choosable.
    home_glow: Mapped[bool | None] = mapped_column(nullable=True)
    # Private per-contact map labelling, keyed by the contact's user id:
    # {"7": {"color": "#c084fc", "icon": "star", "hidden": false}}. The contact
    # never sees any of it — `hidden` only removes their marker from THIS user's
    # map, it does not stop them sharing.
    contact_prefs: Mapped[dict] = mapped_column(JSON, default=dict)
    # Opt-in gamification (collectible-card analysis) — an account-bound setting
    # so toggling it on one device carries to the user's others.
    gamification: Mapped[bool] = mapped_column(default=False)
    # Last authenticated request, stamped by auth/deps.py (throttled). Drives the
    # friend-list presence dot. NULL for accounts that predate the column, which
    # reads as "never seen" — correct, not a special case.
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Gates only the TIMESTAMP ("був о 03:40"), never the live online dot: an
    # activity history is a different disclosure from "is in the app right now".
    # Defaults ON (operator decision) — unlike `share_home`, which stays opt-in
    # because a location is a sharper disclosure than a timestamp.
    share_presence: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    identities: Mapped[list[OAuthIdentity]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Friendship(Base):
    """One directed friendship edge with a consent status. A `pending` row is an
    outstanding request from `requester` to `addressee`; `accepted` means they are
    friends (a single row represents the mutual relationship — queried from either
    side). Reusing one edge (rather than two mirrored rows) keeps accept/remove a
    single-row operation and the unique pair constraint prevents duplicates.
    """

    __tablename__ = "friendships"
    __table_args__ = (
        UniqueConstraint("requester_id", "addressee_id", name="uq_friendship_pair"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # requester_id needs no index of its own — it leads uq_friendship_pair, whose
    # implicit index already serves it; the addressee side is uncovered.
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    addressee_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(10), default="pending")  # 'pending' | 'accepted'
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class OAuthIdentity(Base):
    """One linked SSO provider for a user — lets one account hold
    email+password AND Google AND Telegram at once (linked by verified-email
    match, see app/auth/service.py::get_or_create_user_for_identity).
    """

    __tablename__ = "oauth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_identity_provider_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(20))  # see PROVIDERS
    # Google `sub`; Telegram numeric id as a string.
    provider_user_id: Mapped[str] = mapped_column(String(255))
    # Provider-reported email snapshot at link time (audit only).
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    # Last raw provider payload, for debugging a bad login.
    raw_profile: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="identities")


class PushSubscription(Base):
    """One browser Web Push endpoint + the home zone it wants guarded.

    First client-identity table (single-user MVP, but never assume exactly one
    row). The home zone lives here rather than in its own table because push is
    its only server-side consumer — the map indication recomputes the same
    condition client-side from localStorage (see app/domain/home_danger.py).
    """

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The signed-in owner, when the device subscribed while logged in — lets a
    # user's home/push settings sync across their devices. NULL for anonymous
    # device subscriptions (fully backward-compatible; SET NULL on user delete).
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # The push service URL — unique per browser+SW registration; upsert key.
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    home_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    home_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    home_radius_km: Mapped[float] = mapped_column(Float, default=3.0)
    # Every raion the home CIRCLE meaningfully overlaps (a zone on a boundary
    # sits in 2-3 raions), resolved at subscribe time
    # (home_danger.raion_ids_for_zone) — the ballistic trigger matches any.
    home_district_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    # Notification preferences: {"min_level": "warning"|"danger",
    # "types": [target_type, ...], "citywide": bool}. Absent keys mean the
    # permissive default (warning floor, all types, citywide on) — see
    # home_push._sub_prefs for the single normalization point.
    prefs: Mapped[dict] = mapped_column(JSON, default=dict)
    # Per-track danger bookkeeping so pushes fire on level ESCALATION only:
    # {str(threat_id): {"level": int, "max_pushed": int, "pushed_at": Optional[iso]}}.
    # In DB (not memory) so a Railway redeploy mid-attack doesn't re-push
    # everything. Keys are pruned when their track closes.
    danger_state: Mapped[dict] = mapped_column(JSON, default=dict)
    last_push_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ThreatEvent(Base):
    """A single sighting within a track."""

    __tablename__ = "threat_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    threat_id: Mapped[int] = mapped_column(
        ForeignKey("threats.id", ondelete="CASCADE"), index=True
    )
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"))
    raw_text: Mapped[str] = mapped_column(Text, default="")
    source_message_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    # Parent message id (same source) this sighting replied to — how it was grouped
    # onto its track. NULL for non-threaded posts (grouped by time-gap fallback).
    reply_to_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    # 'rule' | 'llm' | 'sim' — how this structured event was produced.
    decision_source: Mapped[str] = mapped_column(String(10), default="rule")
    # Cached on-demand translation (i18n); source text stays in Ukrainian.
    translated_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Multi-source attribution ---
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("sources.id"), nullable=True, index=True
    )
    # If this message is a repost/forward, the ORIGINAL message id. Two events
    # sharing a forwarded_from_id are the SAME origin — they must not be counted
    # as independent corroboration.
    forwarded_from_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # The ORIGIN channel's Telegram peer id for a repost — see the identical
    # field on RawMessage; carried onto the event so fusion can key on it.
    forwarded_from_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Per-event claimed target type; disagreement across sources => conflict.
    event_target_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Group size KNOWN AS OF this event — the track's running-max target_count at
    # the moment this event landed. The feed shows this (what was known then), not
    # the track's final count, so an early "Ціль на місто!" doesn't retroactively
    # display the ×3 that only a later "3 ракети" established. NULL for pre-column
    # events (the feed falls back to the track's current count for those).
    event_target_count: Mapped[int | None] = mapped_column(nullable=True)
    # Short operator-facing gist from the LLM triage verdict (<=80 chars), when
    # the LLM saw this message — the feed shows it as the card headline with the
    # raw text collapsed beneath. NULL for rule-only events (the vast majority);
    # the feed falls back to raw_text.
    llm_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    threat: Mapped[Threat] = relationship(back_populates="events")
    district: Mapped[District] = relationship()
    source: Mapped[Source | None] = relationship()


class ParserCorrection(Base):
    """A labeled parser mistake, harvested from an admin action in the /admin
    console (see app/domain/corrections.py). Feeds eval/corrections_eval.py — a
    regression check that the CURRENT parser no longer reproduces the mistake.

    `text` is a denormalized snapshot of the raw message so the dataset stays
    self-contained/exportable even if the raw row is ever pruned. Unique on
    (raw_message_id, kind) so re-dismissing the same message upserts, not dupes.
    """

    __tablename__ = "parser_corrections"
    __table_args__ = (
        UniqueConstraint("raw_message_id", "kind", name="uq_correction_raw_kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    raw_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_messages.id", ondelete="SET NULL"), nullable=True
    )
    text: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20))  # see CORRECTION_KINDS
    # What the parser SHOULD have produced: {} / {"suppressed": true} for
    # false_positive, {"target_type": ...} for retype, {"district_id",
    # "district_en"} for relocate.
    expected: Mapped[dict] = mapped_column(JSON, default=dict)
    origin: Mapped[str] = mapped_column(String(20))  # see CORRECTION_ORIGINS
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class GazetteerCandidate(Base):
    """A toponym an admin flagged from the coverage-gap queue (a threat-flavored
    message the parser couldn't localize). Deliberately NOT a live gazetteer
    edit — adding to app/gazetteer.py stays a reviewed code step with a
    stem-collision sweep (CLAUDE.md); this is just the captured candidate.
    """

    __tablename__ = "gazetteer_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    raw_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_messages.id", ondelete="SET NULL"), nullable=True
    )
    text: Mapped[str] = mapped_column(Text)
    suggested_name: Mapped[str] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # see GAZ_CANDIDATE_STATUSES
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


# The two analyses a single target yields over its lifecycle (see gamification):
# one while it's still being tracked, one on its debris after it's shot down.
AnalysisKind = Literal["track", "remains"]
ANALYSIS_KINDS: tuple[AnalysisKind, ...] = get_args(AnalysisKind)


class ThreatAnalysis(Base):
    """One gamification "analysis" of a target — the ledger row that both awards
    a collectible card and enforces the scarcity rule.

    A target yields at most two analyses total (`ANALYSIS_KINDS`): a `track`
    analysis while it flies and a `remains` analysis once destroyed. The
    `UniqueConstraint(threat_id, kind)` makes each of those a *global*
    first-writer-wins claim — the first user to finish analysing that
    threat+kind takes the card; everyone else gets a 409. A user's whole card
    collection is simply their rows here (no separate collection table), so
    `card_id` is the awarded card (1..len(CARD_IDS)) picked uniformly at random.
    """

    __tablename__ = "threat_analyses"
    __table_args__ = (
        UniqueConstraint("threat_id", "kind", name="uq_analysis_threat_kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    threat_id: Mapped[int] = mapped_column(
        ForeignKey("threats.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(10))  # see ANALYSIS_KINDS
    card_id: Mapped[int] = mapped_column()  # 1..len(CARD_IDS), the awarded card
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BugReport(Base):
    """A bug filed from inside the app: what the user saw, optionally a
    screenshot, and the technical context collected for them.

    That context is the whole point. The 2026-08-12 Android report ("everything
    is in the corner") arrived as one screenshot with no version, browser or
    viewport, and the diagnosis had to start by measuring pixels in a JPEG.

    `screenshot` is an inline `data:` URL, validated by app/images.py — same
    trade as avatars: Railway's filesystem is ephemeral, so object storage would
    be a new dependency and a new secret for a handful of rows a year.

    The reporter is kept as a nullable FK: a deleted account must not take the
    bug it reported with it.
    """

    __tablename__ = "bug_reports"
    __table_args__ = (Index("ix_bug_reports_status_created", "status", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    description: Mapped[str] = mapped_column(Text)
    screenshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="new")  # see BUG_REPORT_STATUSES
    # Denormalized for the admin list (shown on every row, filtered on): what
    # the app was, and what it was running in.
    app_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    browser: Mapped[str | None] = mapped_column(String(60), nullable=True)
    os: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # The raw string the two above were derived from — parsing a UA is guesswork
    # and this is what lets a wrong guess be re-read by a human.
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Everything else the client volunteered: route, viewport, dpr, page scale,
    # standalone/PWA, language, online. JSON because this list will keep growing
    # with each class of bug that turns out to need one more number.
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped[User | None] = relationship(lazy="joined")

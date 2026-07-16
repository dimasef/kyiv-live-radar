from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
    boundary: Mapped[Optional[dict]] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )


# Allowed enum-like values kept as plain strings for MVP simplicity.
TARGET_TYPES = ("shahed", "jet_drone", "missile", "ballistic", "unknown")
THREAT_STATUSES = ("unconfirmed", "tracking", "destroyed", "lost", "impact")
# 'track' = an inbound target being followed; 'impact' = a closed-on-creation
# confirmed-strike marker. Split out of `status` (which conflates kind with
# lifecycle) — see app/lifecycle.py.
THREAT_KINDS = ("track", "impact")
# Explicit reason a track closed, replacing `status='lost'`'s three overloaded
# meanings (відбій / дорозвідка stand-down / silence timeout). NULL while open.
CLOSED_REASONS = ("destroyed", "all_clear", "stand_down", "stale")
# Where the structured event came from — critical for parser eval/debugging.
# 'triage' = an async second-pass LLM verdict RESCUED a message the sync rules
# path suppressed/couldn't localize (see app/pipeline/triage.py). Distinct from
# 'llm' (the inline sync fallback that runs while ingest holds the lock).
DECISION_SOURCES = ("rule", "llm", "sim", "triage")
# Async-triage bookkeeping on a raw message (app/pipeline/triage.py). state =
# where the message is in the triage queue's lifecycle; action = what routing
# ultimately did with the verdict. Both NULL for messages never enqueued.
TRIAGE_STATES = ("pending", "done", "skipped", "budget", "error")
TRIAGE_ACTIONS = ("none", "suppress_confirmed", "notice", "axis", "rescue_candidate", "rescued", "late")
# A directional threat axis' lifecycle (app/domain/axes.py). 'unverified' = one
# source only; 'corroborated' = >= axis_min_sources independent sources agreed;
# 'expired' = timed out of the live layer by the sweeper.
AXIS_STATES = ("unverified", "corroborated", "expired")
# Who produced a Notice — a deterministic rule handler or an LLM triage verdict
# (surfaced with an "AI · неперевірено" badge in the feed).
NOTICE_GENERATORS = ("rule", "llm")
# 'spotter' = volunteer sighting channel, parsed by parser.py into
# threats/tracks. 'alert' = official air-raid alert channel (@KyivCityOfficial
# today), parsed by alert_parser.py into Alert rows — routed separately so an
# official "Відбій…" never trips the spotter parser's all-clear and closes
# tracks prematurely (see telegram_listener.py).
SOURCE_ROLES = ("spotter", "alert")
ALERT_SCOPES = ("city", "oblast")
# 'official' = a real відбій from the alert channel; 'failsafe' = the sweeper
# force-closed an alert open past alert_failsafe_hours (dead Telethon session
# ate the відбій, not a real day-long siren) — see app/alerts.py.
ALERT_CLOSED_REASONS = ("official", "failsafe")
# Why an Incident (attack) ended: a spotter's "Відбій" ('all_clear'), the
# official city alert ending ('alert_end'), or the stale sweeper timing it out
# ('stale'). NULL while active — see app/incidents.py.
INCIDENT_ENDED_REASONS = ("all_clear", "alert_end", "stale")


class Source(Base):
    """A monitored Telegram channel (or other feed) that reports sightings.

    Multi-source fusion cross-validates reports across sources. `trust_weight`
    lets known-reliable channels count for more; aggregator/repost channels get
    a low weight so echoing the same original doesn't inflate confidence.
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


class Alert(Base):
    """An official air-raid alert window (тривога -> відбій) from an
    authoritative source (Telegram @KyivCityOfficial today; alerts.in.ua /
    UkraineAlarm later — see `provider`). Independent of Incident: a "silent"
    alert with zero attacks is naturally representable (alert open, zero
    incidents) — linking the two is Phase 3.
    """

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(10))  # 'city' | 'oblast'
    alert_type: Mapped[str] = mapped_column(String(20), default="air_raid")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(20), default="telegram")
    # Provenance — which raw message started/ended this alert, for reprocess.
    started_raw_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("raw_messages.id"), nullable=True
    )
    ended_raw_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("raw_messages.id"), nullable=True
    )
    # 'official' | 'failsafe' (see ALERT_CLOSED_REASONS); NULL while open.
    closed_reason: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)


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
    source_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("sources.id"), nullable=True
    )
    source: Mapped[Optional["Source"]] = relationship()
    message_id: Mapped[Optional[int]] = mapped_column(nullable=True)  # Telegram id
    text: Mapped[str] = mapped_column(Text, default="")
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    forwarded_from_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    # The ORIGIN channel's Telegram peer id, when this message is a repost —
    # `forwarded_from_id` alone is a message id, not globally unique across
    # channels; this disambiguates two different channels whose reposted
    # messages happen to share a numeric id. See fusion.py::_origin_keys.
    forwarded_from_channel_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    # Telegram id of the message this one replies to (same channel). Channels like
    # «Місто Кия | Безпека» reply to the previous post about the SAME target, so the
    # reply chain identifies the track far better than time-proximity does.
    reply_to_message_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    processed: Mapped[bool] = mapped_column(default=False)
    # Whether the LLM fallback (parsing/llm.py) was actually CALLED for this
    # message — distinct from a ThreatEvent's decision_source=='llm' (which
    # also requires the call to have recovered a district; a call that found
    # nothing still spent the API budget). NULL for messages ingested before
    # this column existed — genuinely unknown, not backfillable (unlike
    # Notice.source_message_id, re-deriving this from today's parser/rules
    # would reflect current logic, not what actually ran historically).
    llm_attempted: Mapped[Optional[bool]] = mapped_column(nullable=True)
    # Token usage/cost for that call — set together with llm_attempted=True
    # whenever the API actually responded (see parsing/llm.py::llm_extract).
    # NULL when llm_attempted is False/NULL, or when the call never completed
    # (timeout/network/API error — nothing was billed).
    llm_input_tokens: Mapped[Optional[int]] = mapped_column(nullable=True)
    llm_output_tokens: Mapped[Optional[int]] = mapped_column(nullable=True)
    llm_cost_usd: Mapped[Optional[float]] = mapped_column(nullable=True)
    # The full structured response the LLM fallback returned — district_ids plus
    # the triage fields (category/surface/summary/target_type/status/...). Stored
    # verbatim so LLM calls are auditable on /raw and so the Stage-3 context
    # layer can be tuned against real responses. NULL when the LLM wasn't called
    # or the call produced no usable JSON. COLLECTED-ONLY: nothing in the live
    # pipeline routes on the triage fields yet (see parsing/llm.py::llm_extract).
    llm_response: Mapped[Optional[dict]] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    # Async LLM triage bookkeeping (see TRIAGE_STATES/TRIAGE_ACTIONS and
    # app/pipeline/triage.py). NULL for messages the triage engine never
    # enqueued (rules already localized them, or they were pure junk).
    triage_state: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)
    triage_action: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)


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
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    target_type: Mapped[str] = mapped_column(String(20), default="unknown")
    # Curated origin key (origins.ORIGIN_KEYS) when a toponym was named, else NULL
    # (a bare directional "курсом з півночі" carries only a sector).
    origin_key: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
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
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # 'clear' | 'summary' (rule-emitted) | 'directional' | 'forecast' | 'status'
    # (LLM-triage-emitted context notices — see app/pipeline/triage.py).
    kind: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text, default="")
    target_type: Mapped[str] = mapped_column(String(20), default="unknown")
    source_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("sources.id"), nullable=True
    )
    source: Mapped[Optional["Source"]] = relationship()
    # Original channel message id that produced this notice — same purpose as
    # ThreatEvent.source_message_id, so /raw_messages can trace a raw message
    # to the notice it became (NULL for notices created before this existed).
    source_message_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    # Curated origin key (origins.ORIGIN_KEYS) for a directional notice — the
    # feed clusters same-origin callouts and can point to the matching axis. NULL
    # for non-directional notices.
    origin: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
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
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Time of the most recent member activity — a new threat joins this incident
    # only while this is fresh; the stale sweeper ends the incident once it lapses.
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # NULL while the attack is ongoing; set on all-clear or by the stale sweeper.
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Explicit reason the attack ended (see INCIDENT_ENDED_REASONS); NULL while
    # active, and NULL for historical incidents that ended before this field
    # existed (not backfilled — the real reason isn't recoverable from stored
    # data, unlike Threat.closed_reason's status-derived backfill in Phase 1).
    ended_reason: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
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
    alert_id: Mapped[Optional[int]] = mapped_column(ForeignKey("alerts.id"), nullable=True)
    # How many member messages used decoy/EW vocabulary (see parser.py
    # ParseResult.decoy) — a modifier count, not a replacement classification;
    # an attack can be combined AND partially imitation.
    decoy_mentions: Mapped[int] = mapped_column(default=0)
    # Any member message named a hypersonic system (Кинджал/Циркон/aeroballistic)
    # — a flag on the attack, not a 6th target_type (see parser.py ParseResult.hypersonic).
    has_hypersonic: Mapped[bool] = mapped_column(default=False)

    threats: Mapped[list["Threat"]] = relationship(back_populates="incident")


class Threat(Base):
    """A single target's track, from first sighting to destroyed/lost.

    Fusion fields (corroboration_count / has_conflict / confidence) are derived
    from the track's events across sources — see fusion.py.
    """

    __tablename__ = "threats"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # The attack this track belongs to (Stage E grouping); NULL for pre-incident
    # data or a track not yet attached.
    incident_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("incidents.id"), nullable=True
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
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Explicit reason the track closed (see CLOSED_REASONS) — NULL while open.
    # Replaces status='lost' overloading відбій/дорозвідка/silence-timeout
    # into one meaning; set only via app.domain.lifecycle.close_track().
    closed_reason: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # --- Derived multi-source fusion signals ---
    corroboration_count: Mapped[int] = mapped_column(default=1)  # distinct independent sources
    has_conflict: Mapped[bool] = mapped_column(default=False)    # sources disagree
    confidence: Mapped[float] = mapped_column(Float, default=0.5)  # fused 0..1

    incident: Mapped[Optional["Incident"]] = relationship(back_populates="threats")

    events: Mapped[list["ThreatEvent"]] = relationship(
        back_populates="threat",
        order_by="ThreatEvent.event_time",
        cascade="all, delete-orphan",
    )


class ThreatEvent(Base):
    """A single sighting within a track."""

    __tablename__ = "threat_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    threat_id: Mapped[int] = mapped_column(ForeignKey("threats.id", ondelete="CASCADE"))
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"))
    raw_text: Mapped[str] = mapped_column(Text, default="")
    source_message_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    # Parent message id (same source) this sighting replied to — how it was grouped
    # onto its track. NULL for non-threaded posts (grouped by time-gap fallback).
    reply_to_message_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    # 'rule' | 'llm' | 'sim' — how this structured event was produced.
    decision_source: Mapped[str] = mapped_column(String(10), default="rule")
    # Cached on-demand translation (i18n); source text stays in Ukrainian.
    translated_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- Multi-source attribution ---
    source_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("sources.id"), nullable=True
    )
    # If this message is a repost/forward, the ORIGINAL message id. Two events
    # sharing a forwarded_from_id are the SAME origin — they must not be counted
    # as independent corroboration.
    forwarded_from_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    # The ORIGIN channel's Telegram peer id for a repost — see the identical
    # field on RawMessage; carried onto the event so fusion can key on it.
    forwarded_from_channel_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    # Per-event claimed target type; disagreement across sources => conflict.
    event_target_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # Group size KNOWN AS OF this event — the track's running-max target_count at
    # the moment this event landed. The feed shows this (what was known then), not
    # the track's final count, so an early "Ціль на місто!" doesn't retroactively
    # display the ×3 that only a later "3 ракети" established. NULL for pre-column
    # events (the feed falls back to the track's current count for those).
    event_target_count: Mapped[Optional[int]] = mapped_column(nullable=True)
    # Short operator-facing gist from the LLM triage verdict (<=80 chars), when
    # the LLM saw this message — the feed shows it as the card headline with the
    # raw text collapsed beneath. NULL for rule-only events (the vast majority);
    # the feed falls back to raw_text.
    llm_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    threat: Mapped["Threat"] = relationship(back_populates="events")
    district: Mapped["District"] = relationship()
    source: Mapped[Optional["Source"]] = relationship()

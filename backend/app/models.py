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
# Where the structured event came from — critical for parser eval/debugging.
DECISION_SOURCES = ("rule", "llm", "sim")


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
    message_id: Mapped[Optional[int]] = mapped_column(nullable=True)  # Telegram id
    text: Mapped[str] = mapped_column(Text, default="")
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    forwarded_from_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    # Telegram id of the message this one replies to (same channel). Channels like
    # «Місто Кия | Безпека» reply to the previous post about the SAME target, so the
    # reply chain identifies the track far better than time-proximity does.
    reply_to_message_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    processed: Mapped[bool] = mapped_column(default=False)


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
    kind: Mapped[str] = mapped_column(String(20))  # 'clear' | 'summary'
    text: Mapped[str] = mapped_column(Text, default="")
    target_type: Mapped[str] = mapped_column(String(20), default="unknown")
    source_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("sources.id"), nullable=True
    )
    source: Mapped[Optional["Source"]] = relationship()


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
    # Most severe target type among members (ballistic > missile > jet > shahed).
    target_type: Mapped[str] = mapped_column(String(20), default="unknown")

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
    # Per-event claimed target type; disagreement across sources => conflict.
    event_target_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    threat: Mapped["Threat"] = relationship(back_populates="events")
    district: Mapped["District"] = relationship()
    source: Mapped[Optional["Source"]] = relationship()

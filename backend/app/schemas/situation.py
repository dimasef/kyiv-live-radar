"""Incidents (attacks), notices, official alerts and directional axes."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from ..models import (
    HOME_REGION,
    AlertClosedReason,
    AlertScope,
    AxisState,
    IncidentEndedReason,
    NoticeGenerator,
    NoticeKind,
    Region,
    TargetType,
)
from .base import _as_utc


class IncidentOut(BaseModel):
    """A coordinated attack with counts aggregated from its member threats."""

    id: int
    started_at: datetime
    ended_at: datetime | None = None
    # Why it ended — lets the client drop an admin-cancelled false positive
    # ('dismissed') entirely instead of showing it as a recent attack.
    ended_reason: IncidentEndedReason | None = None
    target_type: TargetType
    status: str  # 'active' | 'ended'
    # Aggregates over member threats (computed in serialize.py::incident_out).
    track_count: int = 0        # inbound tracks (excludes impacts and city alerts)
    # Σ of the stated group sizes over those tracks — what a person means by "how
    # many targets". Larger than track_count whenever a spotter counted a group
    # ("3 долітають до Броварів" is ONE track of three), which is why the banner
    # can't just show track_count under a label that says "цілі". Matches how the
    # journal totals targets, so the two agree.
    target_count: int = 0
    impact_count: int = 0       # distinct confirmed strike locations
    citywide: bool = False      # a city-wide alert is part of this attack
    district_count: int = 0     # distinct raions touched (excludes the sentinel)
    # Distinct raion ids touched by member events (excludes the sentinel) — the
    # frontend highlights these polygons on the map for an active incident.
    district_ids: list[int] = []
    # --- Attack classification (derived — see app/attack.py::classify) ---
    classification: str = "unknown"  # 'drone'|'cruise_missile'|'ballistic'|'combined'|'unknown'
    attack_types: list[str] = []
    alert_id: int | None = None
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
    kind: NoticeKind
    text: str
    target_type: TargetType
    event_time: datetime
    source_id: int | None = None
    source_name: str | None = None
    # Curated origin key for a directional notice (else None) + who produced it
    # ('rule'|'llm'). LLM notices render with an "AI · неперевірено" badge.
    origin: str | None = None
    generated_by: NoticeGenerator = "rule"
    # The reporting channel's region, so the feed's region filter can reach
    # notices too. Read off the source (a notice has no geography of its own —
    # a directional axis names an ORIGIN, not a place in a track pool); no
    # source means the home region, same default as everywhere else.
    region: Region = HOME_REGION

    _tz_notice = field_validator("event_time", mode="before")(_as_utc)


class AlertOut(BaseModel):
    """An official air-raid alert window (тривога -> відбій)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    scope: AlertScope
    alert_type: str
    started_at: datetime
    ended_at: datetime | None = None
    provider: str
    # NULL while the alert is still open.
    closed_reason: AlertClosedReason | None = None

    _tz_alert = field_validator("started_at", "ended_at", mode="before")(_as_utc)


class AxisOut(BaseModel):
    """A directional threat axis for the map's screen-edge wedge layer. Bearing
    and origin display name are derived server-side from the curated origins
    table (app/domain/origins.py) — the client just draws the wedge."""

    id: int
    sector: str            # compass octant
    bearing_deg: int       # 0=N, 90=E — the wedge direction
    origin_key: str | None = None
    origin_name: str | None = None  # display label ("Брянщина"); None for bare-sector
    # Representative centroid of the origin region — the client morphs the edge
    # wedge into an on-map source marker here when it's zoomed out enough to see
    # this spot. None for bare-sector axes (a direction with no named place).
    origin_lat: float | None = None
    origin_lon: float | None = None
    target_type: TargetType
    status: AxisState
    corroboration_count: int = 1
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime | None = None

    _tz_axis = field_validator("created_at", "last_seen_at", "expires_at", mode="before")(_as_utc)

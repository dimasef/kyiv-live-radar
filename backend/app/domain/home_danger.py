"""Danger-near-home assessment for a threat track against a home zone.

Server twin of frontend/src/lib/homeDanger.ts — the client computes the SAME
condition locally for the map indication (home circle color/pulse) while this
module drives Web Push. Change the two together.

Levels:
- DANGER  — an event centroid within home radius + buffer, OR a district-scoped
  ballistic with an event on the raion containing the home zone (sub-minute
  flight time: "балістика на <район дому>" leaves no time to watch a vector).
- WARNING — a moving track whose last-leg forward ray passes through the home
  zone (see vector_threatens).
- NONE    — otherwise. City-wide threats are always NONE here: they endanger
  every point of the city equally and already have the citywide banner.

All geometry runs on district CENTROIDS (see models.District note) — km-scale
coarse, which is why the thresholds carry generous slack.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from typing import Sequence

from sqlalchemy import select

from ..config import settings
from ..models import District, Threat, ThreatEvent
from ..timeutil import naive
from .geometry import angdiff_deg, bearing_deg, haversine_km, point_in_geom


class DangerLevel(IntEnum):
    NONE = 0
    WARNING = 1
    DANGER = 2


@dataclass(frozen=True)
class HomeZone:
    lat: float
    lon: float
    radius_km: float
    # Raion containing the home point, resolved once at subscribe time
    # (raion_id_for_point) — makes the ballistic check an int comparison.
    raion_district_id: int | None = None


@dataclass(frozen=True)
class TrackPoint:
    lat: float
    lon: float
    event_time: datetime


def track_points(events: Sequence[ThreatEvent]) -> list[TrackPoint]:
    """Ordered track points with consecutive repeats dropped (mirror of
    frontend trackPoints). Requires events with district eager-loaded."""
    pts: list[TrackPoint] = []
    for ev in events:
        d = ev.district
        if d is None:
            continue
        if pts and pts[-1].lat == d.lat and pts[-1].lon == d.lon:
            continue
        pts.append(TrackPoint(d.lat, d.lon, ev.event_time))
    return pts


def has_movement(events: Sequence[ThreatEvent]) -> bool:
    """True only if located sightings span >=2 DISTINCT timestamps (mirror of
    frontend hasMovement): one message enumerating several districts produces
    same-time events — an enumeration, not a trajectory."""
    times = set()
    for ev in events:
        if ev.district is None:
            continue
        times.add(naive(ev.event_time))
        if len(times) >= 2:
            return True
    return False


def vector_threatens(pts: list[TrackPoint], home: HomeZone) -> bool:
    """Does the forward ray of the track's last leg pass the home zone?

    With h = last-leg bearing, d = distance(head -> home), β = bearing(head ->
    home), Δ = angdiff(h, β): home must be in front (|Δ| < 90°), within the
    projection horizon, and either the cross-track distance d·sin|Δ| falls
    within radius + slack (the exact test) or |Δ| is within the angular
    tolerance (compensates centroid-derived headings lying by 15–20°).
    """
    if len(pts) < 2:
        return False
    prev, head = pts[-2], pts[-1]
    h = bearing_deg(prev.lat, prev.lon, head.lat, head.lon)
    d = haversine_km(head.lat, head.lon, home.lat, home.lon)
    if d > settings.home_danger_projection_km:
        return False
    beta = bearing_deg(head.lat, head.lon, home.lat, home.lon)
    delta = abs(angdiff_deg(h, beta))
    if delta >= 90:
        return False
    cross_track = d * math.sin(math.radians(delta))
    return (
        cross_track <= home.radius_km + settings.home_danger_pass_slack_km
        or delta <= settings.home_danger_angle_tol_deg
    )


def assess(threat: Threat, home: HomeZone) -> DangerLevel:
    """Danger level of one track for one home zone. Requires the threat's
    events (with districts) eager-loaded."""
    if threat.scope == "city":
        return DangerLevel.NONE
    events = [ev for ev in threat.events if ev.district is not None]
    if not events:
        return DangerLevel.NONE
    danger_radius = home.radius_km + settings.home_danger_buffer_km
    # Proximity is about where the target is NOW: only the latest sighting
    # cluster counts (all events sharing the newest timestamp — one message can
    # enumerate several districts), so a track that passed the home area and
    # moved on stops being DANGER.
    latest = max(naive(ev.event_time) for ev in events)
    for ev in events:
        if naive(ev.event_time) != latest:
            continue
        d = ev.district
        if haversine_km(d.lat, d.lon, home.lat, home.lon) <= danger_radius:
            return DangerLevel.DANGER
    # Ballistic on the home raion: ANY event counts — sub-minute flight means a
    # raion callout is the strike itself, not a passing position.
    if threat.target_type == "ballistic" and home.raion_district_id is not None:
        for ev in events:
            if ev.district_id == home.raion_district_id:
                return DangerLevel.DANGER
    if has_movement(events) and vector_threatens(track_points(events), home):
        return DangerLevel.WARNING
    return DangerLevel.NONE


async def raion_id_for_point(session, lat: float, lon: float) -> int | None:
    """Id of the raion whose OSM boundary contains the point (10 rows with a
    boundary — the admin raions), or None outside all of them."""
    rows = await session.scalars(
        select(District).where(District.boundary.is_not(None))
    )
    for d in rows:
        if point_in_geom(lat, lon, d.boundary):
            return d.id
    return None

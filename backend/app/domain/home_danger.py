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
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum

from sqlalchemy import select

from ..config import settings
from ..models import District, Threat, ThreatEvent, utcnow
from ..timeutil import naive
from .geometry import angdiff_deg, bearing_deg, haversine_km, offset_km, point_in_geom
from .path import path_events, path_head
from .staleness import position_valid_until, reply_tracked_sources


class DangerLevel(IntEnum):
    NONE = 0
    WARNING = 1
    DANGER = 2


@dataclass(frozen=True)
class HomeZone:
    lat: float
    lon: float
    radius_km: float
    # Every raion the home CIRCLE meaningfully overlaps (a zone on a boundary
    # sits in 2-3 raions at once), resolved at subscribe time
    # (raion_ids_for_zone) — the ballistic check is a membership test.
    raion_district_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class TrackPoint:
    lat: float
    lon: float
    event_time: datetime


def track_points(
    events: Sequence[ThreatEvent], path_source_id: int | None = None
) -> list[TrackPoint]:
    """Ordered points of the PATH source's sightings, consecutive repeats
    dropped (mirror of frontend trackPoints). Requires districts loaded."""
    pts: list[TrackPoint] = []
    for ev in path_events(events, path_source_id):
        d = ev.district
        if d is None:
            continue
        if pts and pts[-1].lat == d.lat and pts[-1].lon == d.lon:
            continue
        pts.append(TrackPoint(d.lat, d.lon, ev.event_time))
    return pts


def has_movement(
    events: Sequence[ThreatEvent], path_source_id: int | None = None,
    *, movement_stated: bool = False,
) -> bool:
    """True if the path's located sightings span >=2 DISTINCT timestamps, or a
    stated route gave it two points (mirror of frontend hasMovement): one
    message enumerating several districts produces same-time events — an
    enumeration, not a trajectory."""
    if movement_stated and len(track_points(events, path_source_id)) > 1:
        return True
    times = set()
    for ev in path_events(events, path_source_id):
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


def current_position_events(
    threat: Threat, now: datetime, *, rule: str | None = None
) -> list[ThreatEvent]:
    """The sightings that say where the target IS.

    'legacy': the track's newest cluster (every event at the newest timestamp —
    one message can name several places), however old. 'per_source': each
    source's own newest cluster, kept only while that source's fix is still
    valid (`position_valid_until`) — a narrator quiet for 5 min still places a
    shahed, an echo quiet for 8 min no longer does, and neither hides the other.
    """
    located = [ev for ev in threat.events if ev.district is not None]
    if not located:
        return []
    rule = rule or settings.danger_rule
    if rule != "per_source":
        latest = max(naive(ev.event_time) for ev in located)
        return [ev for ev in located if naive(ev.event_time) == latest]
    narrators = reply_tracked_sources(threat)
    latest_by_source: dict = {}
    for ev in located:
        t = naive(ev.event_time)
        if ev.source_id not in latest_by_source or t > latest_by_source[ev.source_id]:
            latest_by_source[ev.source_id] = t
    out = []
    for ev in located:
        if naive(ev.event_time) != latest_by_source[ev.source_id]:
            continue
        valid_until = position_valid_until(
            threat, ev, narrators=narrators,
            orphan_windows=settings.stale_minutes_orphan,
            tracked_windows=settings.stale_minutes_tracked,
            default_minutes=settings.track_stale_minutes,
        )
        if naive(valid_until) > naive(now):
            out.append(ev)
    return out


def assess(
    threat: Threat, home: HomeZone, now: datetime | None = None
) -> tuple[DangerLevel, ThreatEvent | None]:
    """Danger level of one track for one home zone, with the sighting that
    triggered it: the nearest current fix for DANGER, the raion hit for a
    ballistic, the path head for WARNING. Requires the threat's events (with
    districts) eager-loaded."""
    if threat.scope == "city":
        return DangerLevel.NONE, None
    events = [ev for ev in threat.events if ev.district is not None]
    if not events:
        return DangerLevel.NONE, None
    now = now if now is not None else utcnow()
    danger_radius = home.radius_km + settings.home_danger_buffer_km
    nearest = None
    nearest_km = None
    for ev in current_position_events(threat, now):
        d = ev.district
        km = haversine_km(d.lat, d.lon, home.lat, home.lon)
        if km <= danger_radius and (nearest_km is None or km < nearest_km):
            nearest, nearest_km = ev, km
    if nearest is not None:
        return DangerLevel.DANGER, nearest
    # Ballistic on a home raion: ANY event counts — sub-minute flight means a
    # raion callout is the strike itself, not a passing position.
    if threat.target_type == "ballistic" and home.raion_district_ids:
        for ev in events:
            if ev.district_id in home.raion_district_ids:
                return DangerLevel.DANGER, ev
    psid = threat.path_source_id
    if (
        has_movement(events, psid, movement_stated=threat.movement_stated)
        and vector_threatens(track_points(events, psid), home)
    ):
        return DangerLevel.WARNING, path_head(events, psid)
    return DangerLevel.NONE, None


# Disc sample for zone->raion resolution: center + inner ring + edge ring.
# Each point is (radius_fraction, bearing_deg); the share of points landing in
# a raion approximates the share of the zone's area there. MUST stay identical
# to the frontend mirror (lib/homeDanger.ts ZONE_SAMPLE).
ZONE_SAMPLE: list[tuple[float, float]] = (
    [(0.0, 0.0)]
    + [(0.5, i * 45.0) for i in range(8)]
    + [(1.0, i * 22.5) for i in range(16)]
)


async def raion_ids_for_zone(
    session, lat: float, lon: float, radius_km: float
) -> list[int]:
    """Ids of every raion the home circle meaningfully overlaps: sample the
    disc, count hits per raion (10 boundary rows — the admin raions), keep
    raions with at least home_danger_raion_overlap_min of the samples. A zone
    that barely clips a neighbouring raion stays out."""
    rows = list(await session.scalars(
        select(District).where(District.boundary.is_not(None))
    ))
    hits: dict[int, int] = {}
    for frac, brg in ZONE_SAMPLE:
        km = frac * radius_km
        p_lat, p_lon = offset_km(
            lat, lon,
            north_km=km * math.cos(math.radians(brg)),
            east_km=km * math.sin(math.radians(brg)),
        )
        for d in rows:
            if point_in_geom(p_lat, p_lon, d.boundary):
                hits[d.id] = hits.get(d.id, 0) + 1
                break
    min_hits = settings.home_danger_raion_overlap_min * len(ZONE_SAMPLE)
    return sorted(did for did, n in hits.items() if n >= min_hits)

from __future__ import annotations

"""Small GeoJSON / spherical helpers (no shapely dependency)."""

import math

EARTH_RADIUS_KM = 6371.0


def _outer_ring(geom: dict) -> list:
    """Largest outer ring of a Polygon / MultiPolygon (coords are [lon, lat])."""
    if geom["type"] == "Polygon":
        return geom["coordinates"][0]
    if geom["type"] == "MultiPolygon":
        return max((poly[0] for poly in geom["coordinates"]), key=len)
    return []


def centroid(geom: dict) -> tuple[float, float]:
    """Area-weighted centroid of a polygon's outer ring, returned as (lat, lon)."""
    ring = _outer_ring(geom)
    if len(ring) < 3:
        return (0.0, 0.0)
    a = cx = cy = 0.0
    for i in range(len(ring) - 1):
        x0, y0 = ring[i]
        x1, y1 = ring[i + 1]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if a == 0:  # degenerate — fall back to vertex average
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        return (sum(ys) / len(ys), sum(xs) / len(xs))
    a *= 0.5
    return (cy / (6 * a), cx / (6 * a))  # (lat, lon)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two points."""
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lon2 - lon1)
    h = math.sin(dφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial compass bearing from point 1 to point 2 (0 = north, 90 = east).

    Same formula as frontend lib/geo.ts::bearing — the two must agree.
    """
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dλ = math.radians(lon2 - lon1)
    y = math.sin(dλ) * math.cos(φ2)
    x = math.cos(φ1) * math.sin(φ2) - math.sin(φ1) * math.cos(φ2) * math.cos(dλ)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def offset_km(lat: float, lon: float, north_km: float, east_km: float) -> tuple[float, float]:
    """Point displaced from (lat, lon) by km along the north/east axes.
    Equirectangular approximation — fine at city scale."""
    km_per_deg_lat = math.pi / 180 * EARTH_RADIUS_KM
    return (
        lat + north_km / km_per_deg_lat,
        lon + east_km / (km_per_deg_lat * math.cos(math.radians(lat))),
    )


def angdiff_deg(a: float, b: float) -> float:
    """Signed smallest difference a-b between two bearings, in (-180, 180]."""
    d = (a - b) % 360
    return d - 360 if d > 180 else d


def point_in_geom(lat: float, lon: float, geom: dict) -> bool:
    """Ray-cast point-in-polygon over the outer ring(s) of a GeoJSON
    Polygon/MultiPolygon; holes ignored — deliberate mirror of the frontend's
    coarse check (lib/geo.ts::inRing / districtAt)."""
    if geom["type"] == "Polygon":
        polys = [geom["coordinates"]]
    elif geom["type"] == "MultiPolygon":
        polys = geom["coordinates"]
    else:
        return False
    for rings in polys:
        if rings and _in_ring(lat, lon, rings[0]):
            return True
    return False


def _in_ring(lat: float, lon: float, ring: list) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside

from __future__ import annotations

"""Small GeoJSON helpers (no shapely dependency)."""


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

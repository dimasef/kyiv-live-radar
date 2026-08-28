"""Which region a lat/lon falls in, from the committed oblast outlines.

Answers "where am I" for a home point, which is what turns a device's location
into the region whose tracks should wake it (see pipeline/home_push.py). Reuses
`app/data/region_outlines.json` — the same file the map's oblast layer draws —
so there is no second source of truth for where a border runs.

Ray casting rather than a geometry library: the backend has none, the polygons
are already simplified for display, and the only question asked of them is
which of five large, non-overlapping shapes contains a point. Simplification
makes a border-straddling point ambiguous by a few hundred metres; nothing here
is precise enough for that to matter, and a wrong answer degrades to "the
neighbouring oblast", never to a crash.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..regions import Region

_OUTLINES_FILE = Path(__file__).resolve().parents[1] / "data" / "region_outlines.json"


@lru_cache(maxsize=1)
def _outlines() -> dict[str, dict]:
    if not _OUTLINES_FILE.exists():
        return {}
    return json.loads(_OUTLINES_FILE.read_text("utf-8"))


def _in_ring(lon: float, lat: float, ring: list) -> bool:
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > lat) != (y2 > lat):
            crossing = (x2 - x1) * (lat - y1) / (y2 - y1) + x1
            if lon < crossing:
                inside = not inside
    return inside


def _in_geometry(lon: float, lat: float, geom: dict) -> bool:
    polygons = (
        [geom["coordinates"]] if geom.get("type") == "Polygon" else geom.get("coordinates", [])
    )
    for poly in polygons:
        if not poly:
            continue
        # Ring 0 is the outer boundary, the rest are holes. Kyiv oblast's
        # polygon has the city cut out of it, and the city is a separate part of
        # the same MultiPolygon — so the hole is covered rather than a gap.
        if _in_ring(lon, lat, poly[0]) and not any(_in_ring(lon, lat, h) for h in poly[1:]):
            return True
    return False


def region_at(lat: float, lon: float) -> Region | None:
    """The watched region containing this point, or None if it is outside all of
    them. None is a real answer — most of the country is not watched — and
    callers must treat it as "no region", never as the home one."""
    for region_id, shape in _outlines().items():
        geom = shape.get("geojson")
        if geom and _in_geometry(lon, lat, geom):
            return region_id  # type: ignore[return-value]
    return None


def reset_cache() -> None:
    _outlines.cache_clear()

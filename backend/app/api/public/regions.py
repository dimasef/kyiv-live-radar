"""The watched-region catalogue and the oblast outlines drawn over it.

Both are static — the catalogue is code (`app/regions.py`), the outlines a data
file — so there is no session here. Serving the catalogue instead of letting the
client keep its own list is what makes the region picker, the source grouping
and the map layer pick up a newly declared region with no frontend edit.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Query

from ...domain.region_lookup import region_at
from ...regions import HOME_REGION, REGION_SPECS
from ...schemas import RegionAtOut, RegionOut

router = APIRouter()

_OUTLINES_FILE = Path(__file__).resolve().parents[2] / "data" / "region_outlines.json"


@lru_cache(maxsize=1)
def _outlines() -> dict:
    if not _OUTLINES_FILE.exists():
        return {}
    return json.loads(_OUTLINES_FILE.read_text("utf-8"))


@router.get("/regions", response_model=list[RegionOut])
async def regions():
    """Every declared region, home first, in roster order."""
    return [
        RegionOut(
            id=spec.id,
            name_uk=spec.name_uk,
            active=spec.active,
            is_home=spec.id == HOME_REGION,
            center_lat=spec.center[0],
            center_lon=spec.center[1],
            bbox=list(spec.bbox),
        )
        for spec in REGION_SPECS
    ]


@router.get("/regions/at", response_model=RegionAtOut)
async def region_containing(
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
):
    """Which watched region a point falls in.

    A SUGGESTION, not a decision: the first-run picker uses it to pre-select an
    oblast from a browser location, so the common case is one tap. Which region
    a reader follows is always their explicit choice — nothing derives it from a
    coordinate, because a home point and a region answer different questions and
    inferring one from the other made travelling break the alert radius.

    Unauthenticated, because an anonymous session has a location too.
    `region` is null for a point outside every watched region, which is most of
    the country and not an error.
    """
    return RegionAtOut(region=region_at(lat, lon))


@router.get("/regions/geometry")
async def region_geometry():
    """The oblast outlines, passed through verbatim — same `response_model`-less
    shape (and reason) as /alert-zones/geometry: GeoJSON geometry OpenAPI can
    only describe as "an object"."""
    return _outlines()

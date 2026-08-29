"""Alert-zone siren state + the polygons it paints.

State comes straight from the poller's in-memory snapshot (feeds/alert_zones.py)
— nothing is stored, so there is no session here. Geometry is a static file the
client fetches once, and only when it first turns the layer on.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter

from ...domain.alert_zones import OBLAST_REGION
from ...feeds.alert_zones import zones_out
from ...schemas import AlertZoneOut

router = APIRouter()

_GEOMETRY_FILE = Path(__file__).resolve().parents[2] / "data" / "alert_zones.json"


@lru_cache(maxsize=1)
def _geometry() -> dict:
    """The polygon file, with each zone's `region` joined on from the roster.

    Carried here as well as on the state (`AlertZoneOut.region`) because the
    two arrive at different times: geometry is fetched when the layer is first
    switched on, state at boot. The client narrows the layer to the regions the
    reader follows, and reading the region off the state would mean drawing
    nothing at all on the one occasion the state failed to load — losing the
    grey "we don't know" rendering that is the whole point of `stale`.

    Both sides derive it from `OBLAST_REGION`, so this is one table with two
    readers, not two copies to drift apart.
    """
    if not _GEOMETRY_FILE.exists():
        return {}
    shapes = json.loads(_GEOMETRY_FILE.read_text("utf-8"))
    return {
        zone_id: {**shape, "region": OBLAST_REGION[shape["oblast"]]}
        for zone_id, shape in shapes.items()
    }


@router.get("/alert-zones", response_model=list[AlertZoneOut])
async def alert_zones():
    """Current siren state of every watched raion, in roster order."""
    return zones_out()


@router.get("/alert-zones/geometry")
async def alert_zone_geometry():
    """The zone polygons, passed through verbatim — same `response_model`-less
    shape (and reason) as /districts/boundaries: GeoJSON geometry OpenAPI can
    only describe as "an object"."""
    return _geometry()

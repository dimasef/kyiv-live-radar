"""Address search, used when placing a home marker.

A proxy in front of Nominatim rather than a browser call — the reasons (their
User-Agent and rate-limit policy, neither enforceable from a page) are in
app/geocoding.py, along with the throttle and cache that honour it.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from ...geocoding import MIN_QUERY_LEN, search
from ...regions import Region
from ...schemas import GeocodeHitOut

router = APIRouter()


@router.get("/geocode", response_model=list[GeocodeHitOut])
async def geocode(
    q: str = Query(min_length=1, max_length=120),
    # Narrows the OSM lookup to one oblast's bounding box. Optional, and a
    # miss is harmless: without it the search still covers Ukraine, it just
    # answers "Садова 5" with somewhere the reader isn't.
    region: Region | None = None,
):
    """Places matching `q` — our gazetteer first, then OSM."""
    if len(q.strip()) < MIN_QUERY_LEN:
        return []
    return [
        GeocodeHitOut(
            label=hit.label,
            sublabel=hit.sublabel,
            lat=hit.lat,
            lon=hit.lon,
            source=hit.source,
        )
        for hit in await search(q, region)
    ]

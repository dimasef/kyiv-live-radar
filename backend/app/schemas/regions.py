"""The watched-region catalogue (see app/regions.py).

Static metadata, so the client can render region names, group sources and draw
the oblast layer without hardcoding a list that goes stale the moment a region
is added. Outlines are served separately, verbatim from the data file, so they
have no schema here.
"""

from __future__ import annotations

from pydantic import BaseModel

from ..regions import Region


class RegionAtOut(BaseModel):
    """Which watched region contains a point (GET /regions/at)."""

    # None for a point outside every watched region — most of the country. A
    # client must treat that as "no region", never as the home one.
    region: Region | None = None


class RegionOut(BaseModel):
    """One watched region as the client sees it."""

    id: Region
    name_uk: str
    # False while the region is declared but not yet covered — no gazetteer
    # entries and no siren zones. The client may still show it and let the
    # reader add it to the feed; it just has nothing to show yet.
    active: bool
    # The region the radar is about. Its sightings are never filtered out.
    is_home: bool
    center_lat: float
    center_lon: float
    # [south, west, north, east] — what the map fits when this region becomes
    # the one the reader is in.
    bbox: list[float]

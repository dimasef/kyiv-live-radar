"""District list + OSM boundary polygons — static reference data the map loads once."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_session
from ...models import (
    District,
)
from ...schemas import (
    DistrictOut,
)
from ..read_cache import cached_json

router = APIRouter()


@router.get("/districts", response_model=list[DistrictOut])
async def list_districts(session: AsyncSession = Depends(get_session)):
    response = await cached_json(
        "districts", lambda: _render_districts(session), ttl_s=_TTL_S, versioned=False
    )
    response.headers["Cache-Control"] = _BROWSER_CACHE
    return response


@router.get("/districts/boundaries")
async def district_boundaries(session: AsyncSession = Depends(get_session)):
    """Real OSM boundary polygons for districts that have one (the 10 raions)."""
    response = await cached_json(
        "boundaries", lambda: _render_boundaries(session), ttl_s=_TTL_S, versioned=False
    )
    response.headers["Cache-Control"] = _BROWSER_CACHE
    return response


# The gazetteer changes only through seeding at boot, yet every page load
# re-read and re-serialized all ~720 rows (93 KB, ~20 ms of CPU — the single
# most expensive request of a boot). Rendered once per process regardless of
# pipeline writes, refreshed on a long TTL only as a safety net, and a short
# browser max-age so a reload does not even ask.
_TTL_S = 3600
_BROWSER_CACHE = "public, max-age=300"


async def _render_districts(session: AsyncSession) -> bytes:
    rows = await session.scalars(select(District).order_by(District.name_en))
    return TypeAdapter(list[DistrictOut]).dump_json([DistrictOut.model_validate(d) for d in rows])


async def _render_boundaries(session: AsyncSession) -> bytes:
    rows = await session.scalars(
        select(District).where(District.boundary.is_not(None)).order_by(District.name_en)
    )
    return json.dumps(
        [{"id": d.id, "name_uk": d.name_uk, "name_en": d.name_en, "geojson": d.boundary} for d in rows],
        ensure_ascii=False,
    ).encode()

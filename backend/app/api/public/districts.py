"""District list + OSM boundary polygons — static reference data the map loads once."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_session
from ...models import (
    District,
)
from ...schemas import (
    DistrictOut,
)

router = APIRouter()


@router.get("/districts", response_model=list[DistrictOut])
async def list_districts(session: AsyncSession = Depends(get_session)):
    rows = await session.scalars(select(District).order_by(District.name_en))
    return list(rows)


@router.get("/districts/boundaries")
async def district_boundaries(session: AsyncSession = Depends(get_session)):
    """Real OSM boundary polygons for districts that have one (the 10 raions)."""
    rows = await session.scalars(
        select(District).where(District.boundary.is_not(None)).order_by(District.name_en)
    )
    return [
        {"id": d.id, "name_uk": d.name_uk, "name_en": d.name_en, "geojson": d.boundary}
        for d in rows
    ]

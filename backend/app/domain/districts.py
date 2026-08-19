"""Cached district lookups: the city-wide sentinel id (see
gazetteer.CITYWIDE_NAME_EN) and the district -> region map. Both are resolved
once per process — the rows never change after startup seeding.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select

from ..gazetteer import CITYWIDE_NAME_EN
from ..models import HOME_REGION, District, Source

_citywide_id: int | None = None
_regions: dict[int, str] | None = None


async def citywide_district_id(session) -> int | None:
    global _citywide_id
    if _citywide_id is None:
        _citywide_id = await session.scalar(
            select(District.id).where(District.name_en == CITYWIDE_NAME_EN)
        )
    return _citywide_id


async def district_regions(session) -> dict[int, str]:
    """{district_id: region} for every gazetteer row."""
    global _regions
    if _regions is None:
        rows = await session.execute(select(District.id, District.region))
        _regions = {did: region or HOME_REGION for did, region in rows}
    return _regions


async def resolve_region(session, district_ids: Iterable[int], source_id: int | None) -> str:
    """The region a message belongs to.

    The LAST district named wins — the parser orders hits by position, which is
    movement order, so the last one is the target's current position. A drone
    called in as "Чернігівщина → Козелець → Вишгород" is therefore a Kyiv-region
    message, and its track hands over to the Kyiv pool. With no district at all
    ("Відбій", "Чисто!") there is nothing to read a region off, so the reporting
    channel's own region decides — that is what `sources.region` is for.
    """
    ids = list(district_ids)
    if ids:
        by_id = await district_regions(session)
        return by_id.get(ids[-1], HOME_REGION)
    if source_id is not None:
        region = await session.scalar(select(Source.region).where(Source.id == source_id))
        if region:
            return region
    return HOME_REGION


def reset_cache() -> None:
    global _citywide_id, _regions
    _citywide_id = None
    _regions = None

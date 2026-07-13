"""Cached lookup of the city-wide sentinel district id (see
gazetteer.CITYWIDE_NAME_EN) — resolved once per process, the row never
changes after startup seeding.
"""

from __future__ import annotations

from sqlalchemy import select

from ..gazetteer import CITYWIDE_NAME_EN
from ..models import District

_citywide_id: int | None = None


async def citywide_district_id(session) -> int | None:
    global _citywide_id
    if _citywide_id is None:
        _citywide_id = await session.scalar(
            select(District.id).where(District.name_en == CITYWIDE_NAME_EN)
        )
    return _citywide_id


def reset_cache() -> None:
    global _citywide_id
    _citywide_id = None

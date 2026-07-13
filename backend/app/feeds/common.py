"""Shared feed-source startup helper."""

from __future__ import annotations

from sqlalchemy import select

from ..db import SessionLocal
from ..models import District
from ..parsing import DistrictMatcher


async def build_matcher() -> DistrictMatcher:
    """Load all districts and compile a DistrictMatcher — the same
    select(District) -> DistrictMatcher(...) shell every feed source needs
    once at startup."""
    async with SessionLocal() as s:
        districts = list(await s.scalars(select(District)))
    return DistrictMatcher(districts)

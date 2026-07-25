"""Shared feed-source startup helper."""

from __future__ import annotations

from sqlalchemy import select

from ..db import SessionLocal
from ..models import District
from ..parsing import DistrictMatcher


async def build_matcher(session=None) -> DistrictMatcher:
    """Load all districts and compile a DistrictMatcher — the same
    select(District) -> DistrictMatcher(...) shell every feed source needs
    once at startup.

    Pass an existing `session` (e.g. a request's) to build on that connection —
    request handlers must, so they read the same DB as the rest of the request
    (and stay isolated in tests). With none, opens its own SessionLocal (the
    feed-startup callers)."""
    if session is not None:
        districts = list(await session.scalars(select(District)))
        return DistrictMatcher(districts)
    async with SessionLocal() as s:
        districts = list(await s.scalars(select(District)))
    return DistrictMatcher(districts)

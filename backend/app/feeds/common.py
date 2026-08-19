"""Shared feed-source startup helper."""

from __future__ import annotations

from sqlalchemy import select

from ..db import SessionLocal
from ..models import HOME_REGION, REGIONS, District
from ..parsing import DistrictMatcher


async def _load_districts(session=None) -> list[District]:
    if session is not None:
        return list(await session.scalars(select(District)))
    async with SessionLocal() as s:
        return list(await s.scalars(select(District)))


async def build_matcher(session=None, region: str = HOME_REGION) -> DistrictMatcher:
    """Load all districts and compile a DistrictMatcher — the same
    select(District) -> DistrictMatcher(...) shell every feed source needs
    once at startup.

    Pass an existing `session` (e.g. a request's) to build on that connection —
    request handlers must, so they read the same DB as the rest of the request
    (and stay isolated in tests). With none, opens its own SessionLocal (the
    feed-startup callers).

    `region` only breaks homonym ties (see DistrictMatcher) — every matcher
    still knows every place, because a channel on either side of the border
    reports targets crossing it.
    """
    return DistrictMatcher(await _load_districts(session), prefer_region=region)


class RegionMatchers:
    """One compiled matcher per watched region, off a single district load.

    Compiling ~200 stem regexes per region is cheap once at startup and saves
    the live path from choosing between "recompile per message" and "ignore the
    reporting channel's region" — the latter puts a northern «Лебедівка» on a
    Kyiv village 60 km away.
    """

    def __init__(self, districts: list[District]):
        self._by_region = {
            region: DistrictMatcher(districts, prefer_region=region) for region in REGIONS
        }

    def for_region(self, region: str | None) -> DistrictMatcher:
        return self._by_region.get(region or HOME_REGION, self._by_region[HOME_REGION])

    @property
    def default(self) -> DistrictMatcher:
        return self._by_region[HOME_REGION]


async def build_region_matchers(session=None) -> RegionMatchers:
    return RegionMatchers(await _load_districts(session))

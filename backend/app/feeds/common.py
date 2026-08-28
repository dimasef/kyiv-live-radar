"""Shared feed-source startup helper."""

from __future__ import annotations

from collections.abc import Iterable

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
    """Compiled matchers off a single district load, one per distinct binding.

    Compiling ~200 stem regexes is cheap once at startup and saves the live path
    from choosing between "recompile per message" and "ignore the reporting
    channel's region" — the latter puts a northern «Лебедівка» on a Kyiv village
    60 km away.

    Two lookups, and they mean different things:

    - `for_source` is what the live pipeline uses. It restricts the matcher to
      the regions that source is BOUND to, so a channel never pins a place it
      does not cover. Built lazily and memoized: the bindings come from the DB,
      there are a handful of distinct ones, and enumerating every possible
      subset up front would be 2^N matchers for no reason.
    - `for_region` keeps the older tie-break-only behaviour (every matcher still
      knows every place) for the tools that have no single source to read a
      binding off — admin, coverage, reprocess.
    """

    def __init__(self, districts: list[District]):
        self._districts = districts
        self._by_region = {
            region: DistrictMatcher(districts, prefer_region=region) for region in REGIONS
        }
        self._by_binding: dict[tuple[str, frozenset[str]], DistrictMatcher] = {}

    def for_region(self, region: str | None) -> DistrictMatcher:
        return self._by_region.get(region or HOME_REGION, self._by_region[HOME_REGION])

    def for_source(
        self, region: str | None, extra_regions: Iterable[str] | None = None
    ) -> DistrictMatcher:
        """The matcher for a source bound to `region` (primary) plus `extra_regions`.

        The primary stays the homonym tie-break winner and the district-less
        fallback; the extras only widen what is matchable at all.
        """
        primary = region or HOME_REGION
        allowed = frozenset({primary, *(extra_regions or ())})
        key = (primary, allowed)
        matcher = self._by_binding.get(key)
        if matcher is None:
            matcher = DistrictMatcher(
                self._districts, prefer_region=primary, allowed_regions=allowed
            )
            self._by_binding[key] = matcher
        return matcher

    @property
    def default(self) -> DistrictMatcher:
        return self._by_region[HOME_REGION]


async def build_region_matchers(session=None) -> RegionMatchers:
    return RegionMatchers(await _load_districts(session))

"""A source only localizes inside the regions it is bound to.

The rule replaced an asymmetric one (home region sees everything, everyone else
sees only their own). It is only safe because a channel can be bound to more
than one region — without that, enforcing it would have silently deleted the
Kyiv channels' northern narration.
"""

from app.feeds.common import RegionMatchers
from app.parsing.matcher import DistrictMatcher, normalize

# id, name, region — a minimal gazetteer with one place per region plus a real
# cross-border homonym (Лебедівка exists in both Київська and Чернігівська).
DISTRICTS = [
    {"id": 1, "name_uk": "Оболонський", "name_en": "Obolonskyi",
     "aliases": ["оболонь"], "region": "kyiv"},
    {"id": 2, "name_uk": "Любеч", "name_en": "Liubech", "aliases": [], "region": "chernihiv"},
    {"id": 3, "name_uk": "Лебедівка", "name_en": "Lebedivka-K", "aliases": [], "region": "kyiv"},
    {"id": 4, "name_uk": "Лебедівка", "name_en": "Lebedivka-C",
     "aliases": [], "region": "chernihiv"},
    {"id": 5, "name_uk": "Ромни", "name_en": "Romny", "aliases": [], "region": "sumy"},
]


def _ids(matcher: DistrictMatcher, text: str) -> list[int]:
    return [h.district_id for h in matcher.find(normalize(text))]


def _bound(primary: str, *extra: str) -> DistrictMatcher:
    return RegionMatchers(DISTRICTS).for_source(primary, list(extra))


def test_a_single_bound_source_cannot_pin_another_regions_place():
    """The rule the operator asked for: a village outside the binding is ignored
    rather than pinned hundreds of km away."""
    kyiv_only = _bound("kyiv")
    assert _ids(kyiv_only, "ціль над Оболонню") == [1]
    assert _ids(kyiv_only, "ціль над Любечем") == []
    assert _ids(kyiv_only, "ціль над Ромнами") == []


def test_the_home_region_no_longer_sees_everything_by_default():
    """This is the behaviour change. Under the old asymmetric rule a Kyiv-bound
    matcher matched every region's entries; now the binding is the whole
    answer, for the home region as much as for any other."""
    assert _ids(_bound("kyiv"), "над Любечем") == []


def test_a_second_binding_is_what_keeps_the_northern_narration():
    """The Kyiv channels legitimately report the northern approach — 68 stored
    events over Chernihiv raions. Binding them to both regions is what preserves
    those; without it the rule above would have deleted every one."""
    both = _bound("kyiv", "chernihiv")
    assert _ids(both, "ціль над Оболонню") == [1]
    assert _ids(both, "ціль над Любечем") == [2]
    assert _ids(both, "ціль над Ромнами") == []


def test_the_primary_region_still_wins_a_homonym_tie():
    """Лебедівка exists on both sides of the border and nothing in the text tells
    them apart — the reporting channel's PRIMARY region does."""
    assert _ids(_bound("kyiv", "chernihiv"), "над Лебедівкою") == [3]
    assert _ids(_bound("chernihiv", "kyiv"), "над Лебедівкою") == [4]


def test_a_northern_source_is_unaffected():
    """It was already restricted to its own region; the new rule reaches the
    same answer by a different route."""
    north = _bound("chernihiv")
    assert _ids(north, "над Любечем") == [2]
    assert _ids(north, "над Оболонню") == []


def test_for_region_keeps_the_old_asymmetry_for_the_admin_tools():
    """Coverage, /raw and reprocess have no single source to read a binding off,
    so they keep seeing every place — narrowing them would hide real gaps."""
    matchers = RegionMatchers(DISTRICTS)
    assert _ids(matchers.for_region("kyiv"), "над Любечем") == [2]
    assert _ids(matchers.for_region(None), "над Ромнами") == [5]


def test_matchers_are_memoized_per_binding():
    """Bindings come from the DB and there are a handful of distinct ones —
    compiling per message would put ~200 regex builds on the live path."""
    matchers = RegionMatchers(DISTRICTS)
    first = matchers.for_source("kyiv", ["chernihiv"])
    assert matchers.for_source("kyiv", ["chernihiv"]) is first
    # Order of the extras is not part of the identity.
    assert matchers.for_source("kyiv", ["chernihiv", "chernihiv"]) is first
    assert matchers.for_source("kyiv", []) is not first


def test_an_unbound_source_falls_back_to_the_home_region_alone():
    assert _ids(_bound("kyiv"), "над Оболонню") == [1]
    assert _ids(RegionMatchers(DISTRICTS).for_source(None), "над Любечем") == []

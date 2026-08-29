"""Origin extraction from a callout (app/domain/origins.match_origin).

The subject here is WHEN a place name counts as an inbound direction, which is
the whole difference between an axis pointing at us and a mention of somewhere
else. Bearings/sectors are data, covered where they are rendered (test_axes).
"""

import pytest

from app.domain.origins import (
    ORIGIN_BY_KEY,
    match_origin,
    target_elsewhere,
    target_not_kyiv,
)
from app.parsing.matcher import normalize


def _origin(text: str) -> str | None:
    o = match_origin(normalize(text))
    return o.key if o else None


@pytest.mark.parametrize("text,key", [
    ("Загроза балістики з Брянщини", "bryansk"),
    ("Пуски з боку Чорного моря", "black_sea"),
    ("Загроза балістики з району Ростова", "rostov"),
    ("Ракети від Курщини", "kursk"),
])
def test_from_position_is_an_origin(text, key):
    assert _origin(text) == key


@pytest.mark.parametrize("text", [
    "удар по Брянщині",             # someone striking THEM is not a direction at us
    "працює ППО в Брянську",
    "СБУ знищили Ту-95 в Енгельсі",
    "Відбій по Таганрогу",
])
def test_a_bare_mention_alone_is_not_an_origin(text):
    assert _origin(text) is None


# --- Taganrog: 15 corpus mentions, 11 already in from-position ---------------

@pytest.mark.parametrize("text", [
    "Загроза балістики з Таганрогу",
    "+Загроза балістики з Таганрога",
    "Додається загроза з Таганрогу балістична.",
    "Загроза балістики з району Таганрога нам неактуальна.",
])
def test_taganrog_resolves(text):
    """The extractor always matched this shape; there was simply no entry to map
    it to, so every one of the 11 lost its direction."""
    assert _origin(text) == "taganrog"


def test_taganrog_sits_where_its_bearing_says():
    o = ORIGIN_BY_KEY["taganrog"]
    assert o.sector == "SE"
    # Between Міллерово (105°) and Приморсько-Ахтарськ (135°), beside Ростовщина.
    assert 105 < o.bearing_deg < 135


# --- The terse genitive, allowed only where it cannot be a target ------------

@pytest.mark.parametrize("text,key", [
    ("Загроза балістики Курська", "kursk"),
    ("Балістика курська", "kursk"),
    ("Курська балістична", "kursk"),
    ("Загроза балістики Брянськ ‼️", "bryansk"),
    ("У Курщині ракетна небезпека.", "kursk"),
])
def test_a_foreign_launch_region_needs_no_preposition(text, key):
    """The northern channels write the origin in a bare genitive. It is safe for
    these names for one reason: they are never a target."""
    assert _origin(text) == key


@pytest.mark.parametrize("text", [
    "На Чернігівщині ракети. У нас поки почищено.",
    "Сумщина балістика!",
    "Балістика Чернігівська!",
    "новий реактивний на Чернігівщині",
])
def test_a_watched_region_is_never_an_origin_without_the_preposition(text):
    """The other half of the same 11 corpus messages. These name targets over a
    region we WATCH — turning them into an inbound axis would invent a threat.
    Classification comes from the region registry, so a region going active
    reclassifies its origin on its own."""
    assert _origin(text) is None


def test_the_preposition_still_makes_a_watched_region_an_origin():
    """Suppressing the bare form must not cost the explicit one — a target that
    genuinely crosses from the north is the early warning this radar exists for."""
    assert _origin("Група БпЛА з Чернігівщини курсом на Київ") == "chernihiv"


def test_kursom_is_not_kursk():
    """«курс» is Курщина's third stem and sits inside «курсом», the commonest
    word in this feed. Safe behind a preposition, lethal without one — this exact
    message became an axis from Kursk on the first corpus sweep."""
    assert _origin("Ракети курсом на Дніпро, Кременчук") is None
    assert _origin("БпЛА курсом на Бортничі") is None


def test_from_position_wins_over_a_bare_mention():
    """The bare form is consulted only when nothing was in from-position, so it
    can add a direction where there was none but never change one that resolved."""
    assert _origin("Балістика курська, загроза з Брянщини") == "bryansk"


# --- The region guard: an oblast word must not overrule a matched place -------

def _hits(text: str, region: str):
    from app.gazetteer import DISTRICTS
    from app.parsing.matcher import DistrictMatcher
    districts = [dict(d, id=i + 1) for i, d in enumerate(DISTRICTS)]
    m = DistrictMatcher(districts, prefer_region=region,
                        allowed_regions=frozenset({region}))
    return m.find(normalize(text))


def test_a_kharkiv_callout_is_elsewhere():
    """The nominative anyone actually writes. The list carried «харківщин» and
    the Russian «харков» (which catches the genitive «Харкова») but not this, so
    «Ціль на Харків» was not suppressed at all until 2026-08-29."""
    for text in ("Ціль на Харків", "На Харків!", "На Харків поки."):
        assert target_elsewhere(normalize(text)), text


def test_a_sumy_street_named_like_the_oblast_survives_it():
    """«Харківська» is a street in Суми, and a northern channel really did call a
    target over it («Харківська, Хіммістечко, Героїв Крут реактивний італмас»).
    Adding «харків» to the word list without this guard dropped that sighting."""
    text = "Харківська, Хіммістечко, Героїв Крут реактивний італмас"
    hits = _hits(text, "sumy")
    assert [h.name for h in hits] == ["Харківська", "Героїв Крут"]
    assert not target_elsewhere(normalize(text), hits)
    # …and without the hits — i.e. the old region-blind call — it is suppressed.
    assert target_elsewhere(normalize(text))


def test_the_kyiv_massif_survives_it_too():
    text = "Харківський масив"
    hits = _hits(text, "kyiv")
    assert [h.name for h in hits] == ["Харківський масив"]
    assert not target_elsewhere(normalize(text), hits)


def test_a_place_that_names_its_OWN_region_is_not_blanked():
    """The other half, and the one that makes this a guard rather than a mute.
    Ніжин and Прилуки are Чернігівщина's gazetteer entries AND its threat_stems:
    erasing them let a northern target corroborate the Kyiv city alert. Blanking
    every matched place cost 157 corpus messages this way."""
    for text in ("На Ніжин", "Прилуки над містом"):
        hits = _hits(text, "chernihiv")
        assert hits, text
        assert target_not_kyiv(normalize(text), hits), text

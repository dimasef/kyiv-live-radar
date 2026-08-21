"""Unknown-place-name extraction — the input to the coverage-gap queue.

The regression these lock down is the one that motivated the module: a bare
toponym callout with no target type reaching the queue at all. Before this,
`should_fallback` gated the queue and rejected every single one of them.
"""

from __future__ import annotations

import pytest

from app.gazetteer import DISTRICTS
from app.parsing import DistrictMatcher, normalize
from app.parsing.matcher import _CITYWIDE_NAME_EN
from app.parsing.toponyms import is_known_word, rank_candidates, unknown_toponyms


@pytest.fixture(scope="module")
def matcher() -> DistrictMatcher:
    return DistrictMatcher([{"id": i + 1, **d} for i, d in enumerate(DISTRICTS)])


# Real messages from the Chernihiv channel, 2026-08-18..21, still unlocalized
# after the 2026-08-21 gazetteer batch. Each one names a SPACED toponym, which
# `DistrictMatcher` structurally cannot stem (a spaced name never becomes one
# stem) and which has no distinctive single word to alias — so they will stay
# candidates until multi-word matching exists, which makes them stable fixtures.
@pytest.mark.parametrize(
    "text,expected",
    [
        ("Хороше озеро на омбиш", "хороше"),
        ("Червоне озеро", "червоне"),
        ("Бандеролі Тростянка/Велика Доч", "тростянка"),
        ("Шишки на великий щимель", "шишки"),
    ],
)
def test_bare_toponym_callout_is_a_candidate(matcher, text, expected):
    assert expected in unknown_toponyms(text, matcher)


def test_no_target_type_needed(matcher):
    """The whole point of not reusing `should_fallback`: these messages carry no
    type word, so that gate returns False for every one of them."""
    from app.parsing import parse_message
    from app.pipeline.ingest import should_fallback

    for text in ("Шишки", "Червоне озеро"):
        assert should_fallback(parse_message(text, matcher)) is False
        assert unknown_toponyms(text, matcher)


# The 2026-08-21 batch, as a regression guard on the gazetteer itself: these are
# the real callouts that produced nothing before it and must resolve now.
@pytest.mark.parametrize(
    "text",
    [
        "Жукотки",
        "Пльохів",
        "Киїнка третій",
        "Довжик на жукля",
        "На Берестовець",
        "Нехаївка на Бутівку",
        "Титівка на Переходівку дві",
        "Новий Білоус акустика",
        "Великий щимель",
        "Перший на добрянку",
    ],
)
def test_chernihiv_batch_now_localizes(matcher, text):
    assert matcher.find(normalize(text)), text


@pytest.mark.parametrize(
    "text",
    [
        "Відбій тривоги та загрози від БПЛА, стаємо 🟢!",
        "Всім дякую за підтримку 🫶",
        "Три фіксується",
        "Не спостерігаються",
        "З Брянської новий",
        "На Чернігівщині ще 2х",
        "Київ превентивно",
    ],
)
def test_chatter_and_oblasts_are_not_candidates(matcher, text):
    assert unknown_toponyms(text, matcher) == []


def test_known_districts_are_not_candidates(matcher):
    assert unknown_toponyms("Шахед над Троєщиною", matcher) == []
    assert unknown_toponyms("Реактивний на Славутич", matcher) == []


def test_stoplist_would_still_propose_every_known_place():
    """The corpus sweep app/gazetteer.py demands before any new stem lands.

    Asked as: if this place were NOT in the gazetteer yet, would the queue
    propose it? That is the property that matters — a stop word which is also
    the prefix of a real name silently costs us the next such village. Several
    stems are exactly that shape: the numerals alone cover Трипілля ("три"),
    Семиполки ("семи") and Троєщина ("троє"), and «борщ» was rejected from the
    chatter list for eating Борщагівка.

    Checked against `is_known_word` alone, with no matcher: inside
    `unknown_toponyms` the gazetteer is consulted first and would mask the
    collision instead of revealing it.
    """
    mute = [
        d["name_uk"]
        for d in DISTRICTS
        # The city-wide sentinel is the one entry that must NEVER be proposed —
        # "Київ" is not a place the gazetteer is missing, and the matcher skips
        # it on purpose, so the word lists are all that can suppress it.
        if d["name_en"] != _CITYWIDE_NAME_EN
        # A name too short to be a stem at all («ТЕЦ») is matched through
        # vocab._WHOLE_WORD_ALIASES, and the queue's own 4-char floor means it
        # could never be proposed whatever the word lists say. Nothing to guard.
        and any(len(word) >= 4 for word in normalize(d["name_uk"]).split())
        and not any(
            len(word) >= 4 and not is_known_word(word)
            for word in normalize(d["name_uk"]).split()
        )
    ]
    assert mute == []


def test_min_length_matches_the_gazetteer_stem_floor(matcher):
    """DistrictMatcher drops stems under 4 chars, so a shorter candidate could
    not be added even if it were real — proposing it wastes the operator's
    attention."""
    assert unknown_toponyms("На БЦ", matcher) == []


def test_rank_candidates_orders_by_frequency(matcher):
    texts = [
        ("Шишки", 1),
        ("Шишки другий", 2),
        ("На шишки з півночі", 3),
        ("Червоне озеро", 4),
    ]
    ranked = rank_candidates(texts, matcher)
    assert ranked[0]["name"] == "шишки"
    assert ranked[0]["count"] == 3
    # Equal counts fall back to alphabetical, so the order below "шишки" is
    # stable between loads rather than dependent on dict insertion.
    assert [r["name"] for r in ranked[1:]] == ["озеро", "червоне"]
    # The example points back at the FIRST message that named it, so the
    # operator can open the callout in /raw.
    assert ranked[0]["example_raw_message_id"] == 1


def test_is_known_word_uses_parser_vocabulary():
    """Stems come from vocab.NON_TOPONYM_STEMS, so extending the parser's own
    word lists keeps the queue in sync automatically."""
    assert is_known_word("реактивних")  # _JET stem "реактив"
    assert is_known_word("балістики")  # _BALLISTIC stem "баліст"
    assert is_known_word("тривоги")  # _UNSCOPED_CLEAR_WORD "тривог"
    assert not is_known_word("жукотки")


# --- Region-exclusive entries (gazetteer `region_only`) -----------------------
# «ТЕЦ», «вокзал», «летовище» name a real local landmark to BOTH oblasts' watchers.
# `region` alone cannot separate them and `prefer_region` only breaks ties, so a
# lone Chernihiv entry would have claimed all 42 Kyiv «ТЕЦ» mentions too.

def _region_matcher(region: str) -> DistrictMatcher:
    return DistrictMatcher(
        [{"id": i + 1, **d} for i, d in enumerate(DISTRICTS)], prefer_region=region
    )


@pytest.mark.parametrize(
    "text",
    ["Район ТЕЦ два", "ТЕЦ ⚠️⚠️⚠️", "На жд вокзал", "Вектор летовище", "Очисні другий"],
)
def test_northern_landmark_resolves_for_its_own_channel(text):
    hits = _region_matcher("chernihiv").find(normalize(text))
    assert hits, text
    assert all(h.district_id in _region_matcher("chernihiv").region_by_id for h in hits)


@pytest.mark.parametrize("text", ["Район ТЕЦ два", "Вектор летовище", "Очисні другий"])
def test_northern_landmark_is_invisible_to_a_kyiv_channel(text):
    """The failure this prevents: a Kyiv callout pinned 150 km north."""
    assert _region_matcher("kyiv").find(normalize(text)) == []


def test_kyiv_numbered_plants_still_win_their_own_mentions():
    """Regression guard for the reverted bare-"тец" alias: «ТЕЦ - 6» (spaced) once
    matched ТЕЦ-5, turning a message that matched nothing into a wrong pin."""
    m = _region_matcher("kyiv")
    assert [h.name for h in m.find(normalize("ТЕЦ-6/Воскресенка"))][0] == "ТЕЦ-6"
    assert [h.name for h in m.find(normalize("Видубичі/ТЕЦ-5"))][-1] == "ТЕЦ-5"
    assert [h.name for h in m.find(normalize("ТЕЦ - 6"))] == []


def test_region_only_entry_is_hidden_from_the_llm_enum():
    """Dropped from `districts_index` too, so the model cannot pick a place its
    own channel could never be reporting."""
    names = {n for _, n in _region_matcher("kyiv").districts_index}
    assert "Летовище" not in names
    assert "Летовище" in {n for _, n in _region_matcher("chernihiv").districts_index}

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
        # «Тростянка» in this one is gazetteered since the 08-22 batch; the
        # spaced «Велика Доч» next to it is what still has nowhere to go.
        ("Бандеролі Тростянка/Велика Доч", "велика"),
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
        # Same night, 22:20-22:21 — both were suppressed as "не про загрозу",
        # since a message with no district and no target word is not a threat.
        "Замглай два",
        "Ріпки Замглай два з півночі",
        # The feed's spelling («Голинка») is not the village's («Голінка»).
        "Голинка акустика",
        # The 08-22 batch — the ring around Чернігів and the corridor villages.
        "Гірманка,жукотки",
        "Мекшунівка третій",
        "На Клубівку/Олександрівку другу ➡️ Любеч",
        "Кучугури на наумівку , сновськ",
        "Ряшки на сухополівку",
        "Слобода трисвятська",
        "Турʼя дрон",
        # Both kept as WHOLE-WORD entries, because their stems are ordinary
        # words — the assertion below is the other half of that guard.
        "Замістя на Прилуки",
        "Розсудів",
        # 08-22 morning run, Бахмач → Борзна → Ніжин → Носівка. «Бобрик» is the
        # ROOT of the reply chain «На Держанівку» hangs off, so losing it cost
        # the whole track, not one dot.
        "На Держанівку",
        "На кунашівку",
        "На вересоч курсом",
        "Йде волосківці на локнисте",
        "Маличина гребля",
        "Хатилова гута",
        "Костобобрів розвідник",
        "Східніше Богданове теж",
        "Стольне",
        "Вовчок",
        "Бандеролі на прогрес",
        # A short vowel-final name: inflection replaces the vowel the stem had
        # to keep, so «Ічню» shares no stem with «Ічня» — 5 real messages.
        "На Ічню",
        "Ічні",
    ],
)
def test_chernihiv_batch_now_localizes(matcher, text):
    assert matcher.find(normalize(text)), text


@pytest.mark.parametrize(
    "text",
    [
        "Маленькі кияни замість відпочинку допомагають прибирати",
        "Чи варто реагувати — вирішуйте на власний розсуд",
    ],
)
def test_a_village_named_like_an_ordinary_word_matches_whole_word_only(matcher, text):
    """«Замістя» and «Розсудів» stem to «заміст» and «розсуд», which live inside
    «замість» and «на власний розсуд» — both real corpus sentences. They are in
    _WHOLE_WORD_ALIASES, so the toponym keeps working while the ordinary word
    stays invisible; this is the Остер/остерігайтеся fix reused."""
    assert matcher.find(normalize(text)) == []


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
    ["Район ТЕЦ два", "ТЕЦ ⚠️⚠️⚠️", "На жд вокзал", "Вектор летовище", "Очисні другий",
     # 08-22: two more plants that define a Chernihiv city area, and four
     # village names so common that a Kyiv channel typing one means its own.
     "Автозавод район", "Хімволокно", "Брусилів реактивний", "Дачне",
     "Ще один Іванівка на охрамієвичі",
     # 08-22: «Бобрик» is also a Броварський village beside Велика Димерка, and
     # «Городище» exists five times in this oblast alone.
     "Бобрик", "Городище"],
)
def test_northern_landmark_resolves_for_its_own_channel(text):
    hits = _region_matcher("chernihiv").find(normalize(text))
    assert hits, text
    assert all(h.district_id in _region_matcher("chernihiv").region_by_id for h in hits)


@pytest.mark.parametrize(
    "text",
    ["Район ТЕЦ два", "Вектор летовище", "Очисні другий",
     "Автозавод район", "Брусилів реактивний", "Дачне", "Бобрик", "Городище"],
)
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


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # 2026-08-26, 9 s apart on the Chernihiv channel: one target walked
        # between two Куликівка villages 4.5 km apart and NEITHER callout
        # matched anything, so the map showed no dot and no route at all.
        ("Глузди", "Глузди"),
        ("Горбове", "Горбове"),
    ],
)
def test_kulykivka_pair_localizes(text, expected):
    assert [h.name for h in _region_matcher("chernihiv").find(normalize(text))] == [expected]


@pytest.mark.parametrize(
    "text",
    ["Заспа 🔴.", "Заспа/Сади 🔴.", "Акустично БПЛА район Заспи/Сади/ТЕЦ 🔴.",
     "Той реактивний на Гнідин/Заспу 🔴.",
     "Йдуть по Дніпру через Заспу на південь Києва."],
)
def test_bare_zaspa_reaches_koncha_zaspa(text):
    """The Kyiv channel's habitual terse form. It was dropped for the life of the
    project — 15 corpus mentions, every one of them silent — because a bare
    «Заспа» entry was rejected over a second village 45 km south. Riding on
    Конча-Заспа's aliases keeps that rejection intact: no new point exists."""
    assert "Конча-Заспа" in [h.name for h in _region_matcher("kyiv").find(normalize(text))]


@pytest.mark.parametrize(
    "text", ["На Гути", "Мньов на Гути", "Неданчичі на Гути"],
)
def test_plural_huty_resolves_to_the_northern_pair(text):
    """Decoded from the channel's own corridor bulletin, which spells the stage
    out as «Славутич/Неданчичі ➡️ Боровики/Гути ➡️ Десна/Остер». Боровики is
    2.1 km from Василева Гута; Лошакова Гута is 30 km on and belongs to the
    NEXT stage, 14 km from Десна. GAZETTEER.md had this filed as undecodable."""
    assert "Василева Гута" in [
        h.name for h in _region_matcher("chernihiv").find(normalize(text))
    ]


def test_named_huta_villages_keep_their_own_callouts():
    """The plural must not swallow the three singulars — each is named in full
    when the spotter means that one, and they are up to 30 km apart."""
    m = _region_matcher("chernihiv")
    for text, expected in (
        ("На лошакову гуту", "Лошакова Гута"),
        ("Борсуків на Лошакову Гуту", "Лошакова Гута"),
        ("Хатилова гута", "Хатилова Гута"),
        ("На василеву гуту", "Василева Гута"),
    ):
        assert expected in [h.name for h in m.find(normalize(text))], text


@pytest.mark.parametrize(
    "text", ["Стоянка", "Стоянка 🔴.", "Стоянка увага!", "Стоянка, Романівка"],
)
def test_stoianka_localizes(text):
    """2026-08-27: four channels called it on one western approach and every
    message died as «не про загрозу». The nearest entry was Ірпінь, 7.8 km off."""
    assert "Стоянка" in [h.name for h in _region_matcher("kyiv").find(normalize(text))]


def test_stoianka_does_not_eat_a_parking_lot():
    """The reason this name was a risk at all. «автостоянка» is structurally
    safe (the matcher anchors on a word start); the bare noun is not, so it is
    pinned here — the entry rides on a clean sweep, not on an assumption."""
    m = _region_matcher("kyiv")
    assert [h.name for h in m.find(normalize("Пошкоджено автостоянку"))] == []
    assert [h.name for h in m.find(normalize("біля автостоянки"))] == []


def test_koncha_zaspa_does_not_double_match():
    """The spelled-out name contains the alias. Both branches belong to one
    entry, so the matcher must still return a single hit — two would enumerate
    one place into two targets."""
    m = _region_matcher("kyiv")
    for text in ("Конча-Заспа", "конча заспа"):
        assert [h.name for h in m.find(normalize(text))] == ["Конча-Заспа"], text


def test_no_entry_is_listed_twice():
    """A duplicate is invisible at runtime — DistrictMatcher keeps one hit per
    match offset, so the second copy just never fires — but it means two ids for
    one place, and `seed.py` upserts on name_en, so a repeated name_en silently
    overwrites the earlier row instead of adding one.

    Shipped once (2026-08-24: Блистова, Дуболугівка and Омбиш were re-added by a
    batch that had already been mined against an older gazetteer), which is why
    this is a test and not a note in GAZETTEER.md.
    """
    for field in ("name_en", "name_uk"):
        seen: dict[str, int] = {}
        for d in DISTRICTS:
            seen[d[field]] = seen.get(d[field], 0) + 1
        dupes = {k: n for k, n in seen.items() if n > 1}
        if field == "name_uk":
            # A shared name_uk is legitimate for a cross-border homonym, but only
            # when the two carry different coordinates AND distinct name_en.
            for name in list(dupes):
                rows = [d for d in DISTRICTS if d["name_uk"] == name]
                if len({(d["lat"], d["lon"]) for d in rows}) == len(rows):
                    del dupes[name]
        assert dupes == {}, f"duplicate {field}: {dupes}"


# --- Сумщина, 2026-08-28 -----------------------------------------------------
# Every one of these pins a decision the gazetteer pass made against real corpus
# evidence. They are here so the next pass has to argue with the evidence rather
# than with a red build.

@pytest.mark.parametrize(
    "text,expected",
    [
        # A stem that is an ordinary word, shipped whole-word instead.
        ("Реактивний шах курсом на Терни", ["Терни"]),
        ("Шахед крутиться над районом", []),          # not Героїв Крут
        ("Ще 1 крутяться, слідкуємо", []),
        ("Героїв Крут, Лушпи молнія", ["Героїв Крут", "Лушпи"]),
        ("Річки, Білопілля 2 невідомих БпЛа", ["Білопілля", "Річки"]),
        ("Річка «Либідь» пофарбувалася", []),          # the collision that found it
        ("Пуски КАБ в напрямку Річківської громади", ["Річки"]),
        ("Тополя, Верхнє Піщане увага по fpv", ["Піщане", "Тополя"]),
        ("Сад, Роменська уважно по fpv", ["Сад"]),
        # Спаced names that ride on the FIRST word plus the noun after it.
        ("Долітають до Вакалівщини курсом на Зелений Гай", ["Вакалівщина", "Зелений Гай"]),
        ("яскраво зелений колір", []),
        ("Блакитні Озера, Героїв Крут уважно", ["Блакитні Озера", "Героїв Крут"]),
        ("Повз Сумихімпром курсом на Старе Село", ["Старе Село", "Сумихімпром"]),
        ("старе відео з минулого тижня", []),
        # Проспект Перемоги needs the word BEFORE it; a village Перемога and
        # «заради нашої перемоги» must not reach it.
        ("Далі на Суми, Проспект Перемоги", ["Проспект Перемоги", "Суми"]),
        ("робить усе можливе заради нашої перемоги", []),
        # The city stops at the word boundary — the plant is a target of its own.
        ("Ще ракета на Суми", ["Суми"]),
        ("Окупанти атакували промислову зону в Сумах", ["Суми"]),
        ("Хімпром далі", ["Сумихімпром"]),
    ],
)
def test_sumy_stems_that_are_also_ordinary_words(text, expected):
    hits = _region_matcher("sumy").find(normalize(text))
    assert sorted({h.name for h in hits}) == sorted(expected), text


def test_velyka_pysarivka_never_becomes_the_border_village():
    """80 km apart, and «писарівк» is the only word either of them has.

    A veto keyed by the WORD could only protect one of them, so the qualified
    form was left unlocalized (24 corpus callouts against the bare village's 41).
    Each entry now states its own half of the qualifier as `match_context`, so
    both localize and neither can become the other.
    """
    m = _region_matcher("sumy")
    assert [h.name for h in m.find(normalize("Болото > Писарівка реактивний шах"))] \
        == ["Писарівка"]
    assert [h.name for h in
            m.find(normalize("1 реактивний з Харківщини, курсом на Велику Писарівку"))] \
        == ["Велика Писарівка"]
    assert [h.name for h in m.find(normalize("Обстріл у Великописарівській громаді"))] \
        == ["Велика Писарівка"]


def test_the_two_syrovatky_need_their_qualifier():
    """9 km apart, sharing «сироватк». The alias sat on Верхня alone, so every
    Нижня callout silently landed on Верхня — a wrong pin rather than a gap.
    An unqualified «Сироватка» now matches neither and reaches the coverage
    queue, which is the trade GAZETTEER.md prescribes."""
    m = _region_matcher("sumy")
    assert [h.name for h in m.find(normalize("на Верхню Сироватку"))] == ["Верхня Сироватка"]
    assert [h.name for h in m.find(normalize("ціль на нижню сироватку"))] == ["Нижня Сироватка"]
    assert m.find(normalize("Сироватка")) == []


def test_chernihiv_raion_is_not_the_village_126_km_away():
    """«Деснянський район» is the left-bank raion of the city of Chernihiv;
    Деснянське is a village near Novhorod-Siverskyi. They share «деснянськ», and
    the village had it to itself. The raion is `region_only` because Kyiv has a
    Деснянський of its own — see the Kyiv assertion in test_regions."""
    m = _region_matcher("chernihiv")
    assert [h.name for h in m.find(normalize("На Деснянський р-н"))] == ["Деснянський район"]
    assert [h.name for h in m.find(normalize("Деснянський район єППО"))] == ["Деснянський район"]
    assert [h.name for h in m.find(normalize("Мезин, деснянське"))] == ["Мезин", "Деснянське"]


@pytest.mark.parametrize("text", ["Ціль на Суми.", "Маневр по трасі Київ-Суми.",
                                  "Глухів", "Великий Бобрик"])
def test_sumy_place_is_invisible_to_a_kyiv_channel(text):
    """A Kyiv channel writes these only as somewhere else. Before `region_only`
    each one drew a live target 300+ km away on the Kyiv map."""
    assert _region_matcher("kyiv").find(normalize(text)) == []


@pytest.mark.parametrize("name", ["Суми", "Шостка", "Конотоп", "Ворожба", "Кияниця",
                                  "Миколаївка", "Постольне", "Сумихімпром"])
def test_the_stoplist_would_still_have_proposed_the_sumy_batch(name):
    """Eight of the new entries were muted by a word list that predates them —
    «суми»/«шостк»/«конотоп» as far-away oblast centres, and «миколаїв», «кияни»,
    «пост», «ворож» as prefixes of ordinary words. The queue that is supposed to
    surface a missing village could not have surfaced any of these."""
    assert any(not is_known_word(w) for w in normalize(name).split() if len(w) >= 4)

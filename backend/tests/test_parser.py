"""Parser unit tests on realistic Kyiv-monitoring phrasing."""

from app.gazetteer import DISTRICTS
from app.parser import DistrictMatcher, parse_message


def _matcher():
    districts = [{"id": i + 1, **d} for i, d in enumerate(DISTRICTS)]
    return DistrictMatcher(districts)


M = _matcher()
# Convenience: district id by English name.
BY_EN = {d["name_en"]: i + 1 for i, d in enumerate(DISTRICTS)}


def names(res):
    return [h.name for h in res.districts]


def test_confirmed_shahed_troieshchyna():
    r = parse_message("🔴 Шахед на Троєщині, курс південний", M)
    assert r.target_type == "shahed"
    assert r.status == "confirmed"
    assert BY_EN["Troieshchyna"] in {h.district_id for h in r.districts}
    assert r.confidence >= 0.8


def test_district_declension_darnytskyi():
    r = parse_message("БпЛА в напрямку Дарницького району", M)
    assert r.target_type == "shahed"
    assert BY_EN["Darnytskyi"] in {h.district_id for h in r.districts}


def test_missile_wins_over_generic_drone():
    r = parse_message("Балістика по Києву, укриття! БпЛА теж у небі", M)
    assert r.target_type == "missile"


def test_jet_drone():
    r = parse_message("Реактивний БпЛА на високій швидкості, Позняки", M)
    assert r.target_type == "jet_drone"
    assert BY_EN["Pozniaky"] in {h.district_id for h in r.districts}


def test_destroyed_closes():
    r = parse_message("Збили ціль над Дніпровським районом", M)
    assert r.status == "destroyed"
    assert BY_EN["Dniprovskyi"] in {h.district_id for h in r.districts}


def test_minus_is_destroyed():
    # Spotter shorthand for a downed target; matched even with no district.
    assert parse_message("Мінус ✅", M).status == "destroyed"
    assert parse_message("мінус ще один", M).status == "destroyed"


def test_target_count_extracted():
    assert parse_message("Знову 2х реактивних БПЛА на Чернігівщині", M).target_count == 2
    assert parse_message("Їх вже 3х, курс з Полтавщини на Черкащину", M).target_count == 3


def test_target_count_unstated_is_none():
    assert parse_message("Шахед над Оболонню", M).target_count is None


def test_target_count_ignores_minutes():
    # "20хв" (20 minutes) must NOT read as a count of 20.
    assert parse_message("Ціль буде через 20хв", M).target_count is None


def test_all_clear():
    r = parse_message("Відбій тривоги в Києві", M)
    assert r.status == "clear"
    assert r.matched  # actionable even without a district


def test_unconfirmed_low_conf():
    r = parse_message("Уточнюється, можливо ще одна ціль в районі Осокорків", M)
    assert r.status == "unconfirmed"
    assert r.is_new_target
    assert r.confidence <= 0.4
    assert BY_EN["Osokorky"] in {h.district_id for h in r.districts}


def test_alias_troya():
    r = parse_message("Шахед над Троєю", M)
    assert BY_EN["Troieshchyna"] in {h.district_id for h in r.districts}


def test_multi_district_order_preserved():
    r = parse_message("🔴 Шахед над Оболонню, курс на Виноградар", M)
    ids = [h.district_id for h in r.districts]
    assert BY_EN["Obolon"] in ids and BY_EN["Vynohradar"] in ids
    # Obolon mentioned first -> appears before Vynohradar (movement order).
    assert ids.index(BY_EN["Obolon"]) < ids.index(BY_EN["Vynohradar"])


def test_new_target_marker():
    r = parse_message("Новий шахед зайшов з півночі на Виноградар", M)
    assert r.is_new_target


def test_no_false_district_on_unrelated_text():
    r = parse_message("Слава ЗСУ! Дякуємо за роботу ППО", M)
    assert r.districts == []
    assert not r.matched


def test_sviatoshyn_alias():
    r = parse_message("Шахед над Святошином", M)
    assert BY_EN["Sviatoshynskyi"] in {h.district_id for h in r.districts}


def test_kab_is_missile():
    assert parse_message("КАБ на Харківський напрямок", M).target_type == "missile"


def test_kab_no_false_positive_on_kabel():
    # "каб" must not match inside "кабель" (a downed power line, not a bomb).
    assert parse_message("Пошкоджено кабель, немає світла", M).target_type != "missile"


def test_aftermath_news_is_not_a_sighting():
    # Consequence/casualty news mentions a district but is NOT a live target.
    for txt in [
        "У Деснянському районі надзвичайники врятували дитину",
        "🔴 У Деснянському районі попередньо постраждала багатоповерхівка — КМВА",
        "У Дарницькому районі від атаки пошкоджено багатоповерхівку",
    ]:
        r = parse_message(txt, M)
        assert not r.matched and r.aftermath and r.districts == [], txt


def test_all_clear_survives_aftermath_words():
    # An all-clear must still close tracks even if phrased with consequence words.
    assert parse_message("Відбій тривоги, наслідки уточнюються", M).status == "clear"


def test_fire_footage_and_funding_news_are_aftermath():
    # Real feed examples that slipped through before _AFTERMATH grew these stems.
    for txt in [
        "Жесть! Кадри зараз пожежі на Трої…",
        "Уряд виділить 3,04 млрд грн на відновлення Вишневого після обстрілу рф",
    ]:
        r = parse_message(txt, M)
        assert not r.matched and r.aftermath and r.districts == [], txt


def test_negation_suppresses_the_district():
    # Real feed examples: explicit denial that a target is at/heading somewhere
    # must NOT be recorded as a sighting there.
    for txt in [
        "Не йде на Оболонь",
        "По третьому без загроз для Борисполя. Він все.",
    ]:
        r = parse_message(txt, M)
        assert not r.matched and r.negated and r.districts == [], txt


def test_negation_does_not_override_destroyed():
    # An explicit destroyed keyword elsewhere still wins over a coincidental
    # negation phrase in the same message ("не летить" = it no longer flies,
    # i.e. it WAS just destroyed there — must not suppress the district).
    r = parse_message("Знищено, більше не летить над Оболонню", M)
    assert r.status == "destroyed" and not r.negated and r.districts != []


def test_siren_only_suppresses_the_district():
    # Real feed examples («Віраж Києва»): a technical siren-status echo that
    # names a district but no target type — must NOT be recorded as a sighting.
    for txt in [
        "+ Бучанський район тривога",
        "Тривога у Вишгородському районі",
        "Сунуть в область, тривога у Вишгородському районі",
    ]:
        r = parse_message(txt, M)
        assert not r.matched and r.siren_only and r.districts == [], txt


def test_siren_word_does_not_suppress_a_real_sighting():
    # The same "тривога" word alongside a stated target type is a real
    # sighting and must NOT be suppressed.
    r = parse_message("У Києві можлива знову тривога. 2х реактивних в район Жукин", M)
    assert r.matched and not r.siren_only and r.districts != []


def test_siren_only_does_not_override_clear_or_destroyed():
    # An explicit clear/destroyed keyword elsewhere still wins over the
    # siren-status wording.
    r = parse_message("Відбій тривоги у Вишгородському районі", M)
    assert r.status == "clear" and not r.siren_only and r.districts != []


def test_street_name_collision_is_not_a_district():
    # Real feed example: a utility-maintenance notice names a street that
    # happens to share the raion's adjectival stem — must not be read as a
    # district sighting (same collision class as Остер/"остерігайтеся").
    r = parse_message(
        "Планова промивка мереж по вулицях: Оболонський проспект, 23-30/51.", M
    )
    assert not r.matched and r.districts == []


def test_street_name_collision_does_not_hide_a_real_district_elsewhere():
    # If the street-collision word occurs but the SAME message also names a
    # real district elsewhere, the real district must still be found.
    r = parse_message(
        "Шахед курсом на Дарницький район, а ще ремонт на Оболонському проспекті", M
    )
    assert names(r) == ["Дарницький"]


def test_day_recap_lowers_confidence_but_keeps_district():
    # Real feed example: a day-summary line ("...під атакою сьогодні") with no
    # target type/vector is soft evidence, not a fresh sighting — keep the
    # district (unlike siren_only) but drop confidence.
    r = parse_message("Знову Деснянський район під атакою сьогодні", M)
    assert r.matched and r.day_recap and names(r) == ["Деснянський"]
    assert r.confidence <= 0.35


def test_political_quote_suppresses_the_district():
    # Real feed examples («ППО - Київ»): a news repost of a Zelensky statement
    # naming a place — not a live spotter sighting.
    for txt in [
        "❗️Я очікую від СБУ і розвідки детального зʼясування того, "
        "що сталось у Вишневому, — Зеленський",
        '❗️ У Вишневому був склад боєприпасів одного з підприємств '
        '"Укроборонпрому", — Зеленський',
    ]:
        r = parse_message(txt, M)
        assert not r.matched and r.political_quote and r.districts == [], txt


def test_political_quote_does_not_suppress_a_real_sighting():
    # A stated target type elsewhere in the same message is a real sighting
    # and must NOT be suppressed, even alongside an official's name.
    r = parse_message(
        "2х шахед курсом на Вишневе — за словами очевидців, Зеленський уже поінформований", M
    )
    assert r.matched and not r.political_quote and r.districts != []


def test_political_quote_does_not_override_clear_or_destroyed():
    # An explicit destroyed keyword elsewhere still wins over the
    # quote-attribution wording, same carve-out as siren_only/negated.
    r = parse_message("Збито над Вишневим, — Ігнат", M)
    assert r.status == "destroyed" and not r.political_quote and r.districts != []


def test_day_recap_word_does_not_lower_a_real_sighting():
    # The same "сьогодні" word alongside a stated target type is a real
    # sighting and must keep normal confidence.
    r = parse_message("2х шахед курсом на Дніпровський район сьогодні вночі", M)
    assert not r.day_recap and r.confidence > 0.35


def test_lost_signal_detected_with_and_without_a_target_type():
    # Real feed examples («ППО - Київ» / «Місто Кия»): "дорозвідка" = ППО no
    # longer has/sees targets of the stated type (or none at all) — a
    # stand-down signal, handled directly by ingest.py, not a suppression.
    for txt in ["Все, Дорозвідка", "Дорозвідка", "Дорозвідка по крилатих ракетах.",
                "По шахедах дорозвідка"]:
        r = parse_message(txt, M)
        assert r.lost_signal and r.districts == [], txt


def test_lost_signal_does_not_swallow_a_concurrent_real_sighting():
    # Real feed example: recon lost for cruise missiles, but a drone is still
    # actively tracked over a named district in the SAME message — must not
    # be treated as a lost_signal (that would drop the real Позняки sighting).
    r = parse_message(
        "Дорозвідка по крилатим ракетам. Залишаються БПЛА. Найближчий в районі Позняки", M
    )
    assert not r.lost_signal and r.matched and names(r) == ["Позняки"]


def test_lost_signal_does_not_override_destroyed():
    # Real feed example: "Мінуснули, Дорозвідка" — one target confirmed
    # destroyed, "дорозвідка" here is a follow-up status note, not a broader
    # stand-down. The explicit destroyed keyword must win (same carve-out as
    # negated/siren_only/political_quote) — otherwise this would incorrectly
    # close EVERY open track as "lost" instead of just the destroyed one.
    r = parse_message("Мінуснули, Дорозвідка", M)
    assert r.status == "destroyed" and not r.lost_signal

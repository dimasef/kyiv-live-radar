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

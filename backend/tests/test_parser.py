"""Parser unit tests on realistic Kyiv-monitoring phrasing."""

from app.gazetteer import DISTRICTS
from app.parsing import DistrictMatcher, parse_message


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


def test_ballistic_wins_over_generic_drone():
    r = parse_message("Балістика по Києву, укриття! БпЛА теж у небі", M)
    assert r.target_type == "ballistic"


def test_ballistic_vs_cruise_missile_are_distinct_types():
    # Ballistic (sub-minute, city-wide) must be a different type from cruise
    # (trackable, draws a vector) — they drive different map behavior.
    assert parse_message("Кинджал на столицю", M).target_type == "ballistic"
    assert parse_message("Загроза застосування балістики", M).target_type == "ballistic"
    assert parse_message("Працює С-400 по місту", M).target_type == "ballistic"
    assert parse_message("Крилаті ракети курсом на Київ", M).target_type == "missile"
    # A bare "ракета" is ambiguous and defaults to the generic missile type.
    assert parse_message("Ракета над Позняками", M).target_type == "missile"


def test_jet_drone():
    r = parse_message("Реактивний БпЛА на високій швидкості, Позняки", M)
    assert r.target_type == "jet_drone"
    assert BY_EN["Pozniaky"] in {h.district_id for h in r.districts}


def test_masculine_one_infers_shahed_when_no_type_stated():
    # Ukrainian numeral agreement: "один"/"одне" (masculine/neuter) implies a
    # masculine-gender noun (шахед/дрон/БПЛА), not "ракета" (feminine). Real
    # feed examples, none of which name a type directly.
    for txt in ["Один на водосховище", "Оболонь 🔴. Один залишився.",
                "ще один на Славутич", "Один збили, залишився ще один"]:
        r = parse_message(txt, M)
        assert r.target_type == "shahed", txt


def test_masculine_one_does_not_override_an_explicit_type():
    # An explicit "реактивний"/"ракета" elsewhere in the message still wins —
    # the gender guess is only a fallback for when nothing else is stated.
    r = parse_message("Залишився один реактивний в ЧЗВ", M)
    assert r.target_type == "jet_drone"
    r = parse_message("Ракета, одна на Позняки", M)
    assert r.target_type == "missile"


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


def test_raion_moria_matches_sea_approach():
    # "район моря" / "на море" — the Kyiv Reservoir's near-northern approach —
    # resolves to the KyivSeaApproach point, across море/моря inflections.
    for txt in ["3х реактивних БПЛА в район моря з Чернігівщини",
                "На море ракети", "Заходить у район моря"]:
        r = parse_message(txt, M)
        assert BY_EN["KyivSeaApproach"] in {h.district_id for h in r.districts}, txt


def test_foreign_sea_not_matched_as_kyiv_approach():
    # "Каспійського/Чорного моря" are bomber launch-zones, not Kyiv's approach —
    # the foreign-sea guard keeps them out (they'd otherwise match "моря").
    for txt in ["У районі Каспійського моря вильоти о 02:30",
                "загроза по Чорному морю"]:
        r = parse_message(txt, M)
        assert BY_EN["KyivSeaApproach"] not in {h.district_id for h in r.districts}, txt


def test_eppo_marks_dismissed_are_suppressed():
    # Real FP: the spotter lists єППО app marks while saying they see nothing —
    # the named districts must NOT become tracked events.
    r = parse_message(
        "У нас справді локаційно не видно, відмітки єППО Вишневе, Макарів, "
        "Шевченківський. В області локаційно дорозвідка.", M)
    assert r.eppo_marks
    assert r.districts == []
    assert not r.matched


def test_eppo_confirmed_target_not_suppressed():
    # A genuine єППО-confirmed sighting (no "not seen" cue) keeps its district.
    r = parse_message("єППО показує ціль на Оболоні, підтверджую своїми джерелами", M)
    assert not r.eppo_marks
    assert BY_EN["Obolon"] in {h.district_id for h in r.districts}


def test_advisory_preview_of_targeted_raions_is_suppressed():
    # Real FP class (07-23, «Віраж Києва»): forecast / relayed-opinion previews
    # listing which raions MIGHT be hit — not live sightings. None may produce a
    # track: relayed rumour, relayed speculation, and a warning bulletin.
    for txt in [
        "Пишуть що також є загроза для Броварів!",
        "По тому що я читав в інших джерелах та бачив, то ймовірно ворога "
        "цікавлять такі райони: Жуляни, Святошин, Дарниця, Оболонь, Борщагівка",
        "Є попередження про використання 35 балістичних ракет Іскандер-М/С-400 "
        "найближчими ночами по м. Київ. Підвищена загроза таким районам: "
        "Видубичі, Борщагівка, Дарниця, Березняки",
    ]:
        r = parse_message(txt, M)
        assert r.negated, txt
        assert r.districts == [], txt
        assert not r.matched, txt


def test_live_probable_type_callout_not_suppressed_as_advisory():
    # "Ймовірно" about the TYPE (not whether it's real) is a genuine live
    # city-wide callout — the advisory markers must not swallow it.
    r = parse_message("Увага ймовірно Циркон на Київ", M)
    assert not r.negated
    assert r.citywide


def test_retrospective_applied_count_is_summary_not_citywide():
    # "Було застосовано ~40 ракет" is a recap of an attack that already happened
    # (no raion) — a summary, must not raise a live city-wide alert.
    r = parse_message(
        "Ймовірно найбільша балістична атака на столицю за весь час. "
        "Було застосовано близько 40 ракет Іскандер-М/Циркон/С-400", M)
    assert r.summary
    assert not r.citywide and not r.matched


def test_applied_count_with_district_stays_a_live_impact():
    # The same "застосован" stem must NOT summarise away a district-bearing
    # strike report — the has_district gate keeps it.
    r = parse_message("Ракета застосована по Троєщині, влучання", M)
    assert not r.summary
    assert "Троєщина" in names(r)


def test_linkless_channel_ad_is_promo():
    # Real FP (raw 1038): a subscribe/recruitment post listing localities but
    # carrying no URL — the link-less promo variant. Must not raise tracks.
    r = parse_message(
        "❗️Вишневе тепер в Telegram\nЯкщо ти живеш у такому населеному пункті:\n"
        "▪️Вишневе ▪️Софіївська Борщагівка ▪️Крюківщина ▪️Чайки ▪️Гатне", M)
    assert r.promo
    assert not r.matched


def test_bilohorodka_matches():
    for txt in ["Білогородка увага по БпЛА", "Один шахед на Білогородку звернув"]:
        r = parse_message(txt, M)
        assert BY_EN["Bilohorodka"] in {h.district_id for h in r.districts}, txt


def test_kab_is_missile():
    assert parse_message("КАБ на Харківський напрямок", M).target_type == "missile"


def test_kab_no_false_positive_on_kabel():
    # "каб" must not match inside "кабель" (a downed power line, not a bomb).
    assert parse_message("Пошкоджено кабель, немає світла", M).target_type != "missile"


def test_localized_strike_is_an_impact_not_suppressed():
    # Both real tonight reports: a confirmed hit that names a district — mapped
    # as an impact marker, NOT dropped as generic aftermath.
    r = parse_message("В Дніпровському районі влучання по нежитловій будівлі", M)
    assert r.impact and not r.aftermath and r.matched
    assert BY_EN["Dniprovskyi"] in {h.district_id for h in r.districts}
    r = parse_message("У Святошинському районі внаслідок атаки пошкоджено нежитлову будівлю.", M)
    assert r.impact and not r.aftermath and r.matched
    assert BY_EN["Sviatoshynskyi"] in {h.district_id for h in r.districts}


def test_impact_wins_over_casualty_words():
    # A strike report that also mentions casualties is still an impact — the
    # location is the useful signal.
    r = parse_message("Приліт у Оболонському районі, є постраждалі", M)
    assert r.impact and not r.aftermath


def test_building_damage_in_a_district_is_now_an_impact():
    # Reclassified by Stage B: "пошкоджено багатоповерхівку в <district>" was
    # previously suppressed as aftermath; a damaged building IS a strike
    # location worth mapping, so it now becomes an impact marker.
    r = parse_message("У Дарницькому районі від атаки пошкоджено багатоповерхівку", M)
    assert r.impact and not r.aftermath and r.matched
    assert BY_EN["Darnytskyi"] in {h.district_id for h in r.districts}


def test_pure_aftermath_without_strike_verb_stays_suppressed():
    # Casualty/rescue/fire news with a district but NO strike verb is still
    # suppressed — it is not a mappable strike location.
    for txt in ["Постраждала багатоповерхівка в Дарницькому районі",
                "Рятувальники ДСНС гасять пожежу на Троєщині"]:
        r = parse_message(txt, M)
        assert r.aftermath and not r.impact and not r.matched, txt


def test_transport_notice_is_suppressed_not_a_target():
    # The T217/M668 FP class: a trolleybus-route / road-closure notice names a
    # neighbourhood the gazetteer matches (Мінський масив) but is city news, not
    # a target — must be dropped, districts cleared.
    for txt in [
        "🚎 Тимчасово змінять маршрути тролейбусів № 6, 16 та 18: "
        "від Мінського масиву до станції метро «Лукʼянівська»",
        "Обмежать рух транспорту завтра у Києві, плануйте маршрут завчасно",
        "Зміни в роботі громадського транспорту: фунікулер зачинять на ремонт",
    ]:
        r = parse_message(txt, M)
        assert r.civic_notice and not r.matched and r.districts == [], txt


def test_real_target_over_a_road_is_not_a_civic_notice():
    # The guard: a NAMED threat (target_type != unknown) is never silenced by a
    # coincidental transport/route word — only type-unknown city news is.
    r = parse_message("Шахед змінив маршрут руху, зайшов на Троєщину", M)
    assert not r.civic_notice and r.matched
    assert BY_EN["Troieshchyna"] in {h.district_id for h in r.districts}


def test_damage_without_district_is_not_an_impact():
    # "пошкодж"/"зруйнов" only become an impact WITH a district; district-less
    # damage news (or a downed cable) stays plain aftermath / no impact.
    r = parse_message("Пошкоджено кабель, немає світла", M)
    assert not r.impact


def test_citywide_threat_detected_without_a_district():
    # The sub-minute ballistic phase: a strike aimed at the whole city, no raion.
    for txt in ["Ціль на місто!", "3х цілі на місто!", "Балістика на Київ",
                "Ракетна небезпека по Києву"]:
        r = parse_message(txt, M)
        assert r.citywide and r.matched and r.districts == [], txt


def test_directional_callout_is_citywide_on_a_kyiv_channel():
    # All monitored channels are Kyiv-dedicated, so a bare directional callout
    # ("На Київ!", "Увага місто!") IS a city-wide threat — no extra keyword.
    for txt in ["На Київ!", "Увага місто!"]:
        r = parse_message(txt, M)
        assert r.citywide and r.matched and r.districts == [], txt


def test_retrospective_attack_summary_is_not_a_live_alert():
    # A recap of the whole attack ("загалом ... 8 ракет", past frame) is info,
    # NOT a live target — it must not raise a city alert.
    for txt in [
        "Загалом по Києву пустили до 8 ракет. Перші цілі не фіксувалися",
        "Росія випустила близько 8 балістичних ракет С-400 по Києву за останні 15 хвилин",
    ]:
        r = parse_message(txt, M)
        assert r.summary and not r.citywide and not r.matched, txt


def test_citywide_needs_threat_context_not_just_a_city_phrase():
    # A city phrase alone (news/greeting/status) is NOT a city-wide threat.
    for txt in ["Новини по Києву за добу", "Слава Києву!",
                "Ситуація по Києву спокійна"]:
        r = parse_message(txt, M)
        assert not r.citywide, txt


def test_citywide_not_triggered_when_a_district_is_named():
    # A localized report is a normal sighting, never a city-wide alert.
    r = parse_message("Балістика на Троєщину", M)
    assert not r.citywide and r.districts != []


def test_city_sentinel_is_not_matchable_as_a_district():
    # A plain "у Києві" must NOT resolve to the city-wide sentinel district.
    r = parse_message("У Києві чути вибухи", M)
    assert r.districts == []


def test_aftermath_news_is_not_a_sighting():
    # Consequence/casualty news (rescue, casualties) with NO strike verb mentions
    # a district but is NOT a live target and NOT a mappable strike location.
    for txt in [
        "У Деснянському районі надзвичайники врятували дитину",
        "🔴 У Деснянському районі попередньо постраждала багатоповерхівка — КМВА",
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


def test_waiting_for_all_clear_is_not_a_clear():
    # "Чекаємо/очікуємо відбій" ANTICIPATES the all-clear — must NOT read as a
    # clear (which would prematurely close every open track). The скоро/надія/
    # очікується forms are real-attack examples that slipped through before.
    for txt in ["Чекаємо на відбій", "Очікуємо відбій",
                "Якщо надалі спокійно — очікуватимемо відбій",
                "Скоріш за все скоро відбій",
                "Є надія на відбій у Києві, тримаємо",
                "В області очікується відбій також",
                "Очікуватимемо на відбій тривоги найближчим часом",
                "Будемо очікувати на відбій.",
                "Чекатимемо відбою найближчим часом."]:
        assert parse_message(txt, M).status != "clear", txt
    # A real all-clear still clears.
    for txt in ["Дали відбій нарешті", "Відбій тривоги та загрози від балістики",
                "Все, в області відбій", "По балістиці відбій"]:
        assert parse_message(txt, M).status == "clear", txt


def test_past_strike_aggregate_is_a_summary_not_a_live_target():
    # "6 балістичних ВДАРИЛО по Києву" recaps what already hit (aggregate, past,
    # no raion) — a summary, not 6 live incoming ballistic targets.
    for txt in ["⏺ Близько 6 балістичних ракет вдарило по Києву, можуть повторно пустити",
                "Вночі всі 30 балістичних ракет вдарили по будинках"]:
        r = parse_message(txt, M)
        assert r.summary and not r.matched, txt
    # But a DISTRICT-bearing single strike stays a live impact/sighting — the
    # has_district gate must keep "вдарила по Троєщині" out of summary.
    r = parse_message("Ракета вдарила по Троєщині, приліт", M)
    assert not r.summary and r.matched and names(r) == ["Троєщина"]


def test_post_strike_fire_is_aftermath():
    # Burning-verb aftermath ("горять/вигорілі") — post-strike fire, not a target.
    for txt in ["В Дарницькому районі горять автомобілі",
                "⏺На Соломі горять офіси після російського удару",
                "У Дарницькому районі горить трансформаторна підстанція"]:
        r = parse_message(txt, M)
        assert r.aftermath and not r.matched and r.districts == [], txt
    # "Вишгород" must NOT trip the burning stems (no згорі/горіл collision).
    assert parse_message("10 БПЛА на Вишгород", M).matched


def test_link_bearing_message_is_promo_not_a_sighting():
    # A URL means promo/donation/ad/meta — never a live spotter sighting.
    for txt in ["Друзі, створив ракетний канал по Києву https://t.me/kyiv_allerts",
                "Ймовірно була фальш ціль. https://t.me/Kyiaradar/2772 — пояснення"]:
        r = parse_message(txt, M)
        assert r.promo and not r.matched, txt
    # A real sighting with no link is untouched.
    assert parse_message("2 шахеди на Троєщину", M).matched


def test_retrospective_footage_is_not_a_live_impact():
    # "На відео наслідки останньої атаки… пошкодження в <district>" is footage
    # of a PAST strike — must NOT create a live impact / attack banner.
    r = parse_message(
        "На відео наслідки останньої атаки в Соломʼянському районі, зафіксовані "
        "пошкодження об'єктів та вибито вікна", M)
    assert not r.impact and not r.matched
    # A genuine fresh strike still reads as an impact.
    assert parse_message("В Дніпровському районі влучання по будівлі", M).impact


def test_zircon_types_as_ballistic():
    # 07-18: a channel that mostly said "циркони" never typed its messages, so
    # its bare toponyms all became "unknown" tracks. Zircon flies the same
    # sub-minute profile — it types as ballistic (and keeps the hypersonic flag).
    r = parse_message("Циркони !!!", M)
    assert r.target_type == "ballistic"
    assert r.hypersonic
    assert r.target_pulse  # terse callout corroborates an open city-wide alert


def test_negated_type_mention_does_not_type():
    # The real 07-18 aside that typed itself as shahed via "це не БПЛА" and
    # poisoned the channel context (the city-wide card spent 15 min as БПЛА).
    r = parse_message(
        "Воно з лівого на правий за кілька секунд, це не БПЛА. "
        "Тому весь Київ уважно.", M)
    assert r.target_type == "unknown"


def test_negated_type_flips_to_the_stated_one():
    r = parse_message("Це не шахед, це балістика!", M)
    assert r.target_type == "ballistic"


def test_non_adjacent_negation_keeps_type():
    # "не притаманна для «Іскандер-М»" negates the verb, not the type — the
    # message genuinely talks about ballistics.
    r = parse_message("Фіксація та траєкторія не притаманна для «Іскандер-М».", M)
    assert r.target_type == "ballistic"


def test_card_number_donation_is_promo():
    # The link-less donation variant ("Моно - 4441…") — its "до останнього
    # Шахеда та ракети" sign-off must not read as a live target.
    r = parse_message(
        "Адмінам на енергетик за працю. Моно - 4441111126308174. "
        "Будемо працювати до останнього Шахеда та ракети", M)
    assert r.promo and not r.matched


def test_blazing_verb_is_aftermath():
    # "палає/палають" — post-strike fire, same class as "горить" ("Вся
    # Лукʼянівка палає.." raised a live ballistic track on 07-19). "впала"
    # (ракета впала) contains the bare stem and must stay live.
    for txt in ["Вся Лукʼянівка палає..",
                "У Святошинському районі палає приватний житловий будинок."]:
        r = parse_message(txt, M)
        assert r.aftermath and not r.matched, txt
    assert not parse_message("Ракета здетонувала, що впала.", M).aftermath
    # A fresh strike report with a fire mention is still an impact.
    assert parse_message("В Дніпровському районі влучання по будівлі, палає дах", M).impact

"""Parser unit tests on realistic Kyiv-monitoring phrasing."""

from app.gazetteer import DISTRICTS
from app.parsing import DistrictMatcher, parse_message
from app.parsing.vocab import _CITYWIDE_BARE_RE


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


def test_jet_drone_stated_as_a_noun():
    # 08-04: the noun form parsed as `unknown` and inherited `ballistic` from
    # the open incident — a drone corridor labelled ballistic on the map.
    for txt in ["3 реактива повз Славутич", "Ще 2 реактива йдуть біля Десни",
                "Новий реактив повз Славутич йде"]:
        assert parse_message(txt, M).target_type == "jet_drone", txt


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


def test_bare_count_heading_for_a_place():
    # The commonest count form in the feed, and it used to be dropped entirely:
    # no "х" suffix and no target noun, just a number and where it's going.
    # All four are real messages.
    assert parse_message("3 на Славутич", M).target_count == 3
    assert parse_message("2 на Бровари, уважно", M).target_count == 2
    assert parse_message("Ще 4 на Бровари", M).target_count == 4
    assert parse_message("2 на Десну", M).target_count == 2


def test_bare_count_needs_a_known_place_after_it():
    # The number only counts when the gazetteer matched what follows it — a bare
    # digit before a preposition is far too common to trust on its own.
    # Real message: the "3" belongs to the bomber designation Ту-22м3.
    assert (
        parse_message(
            "Нагадаю, що загроза по Ту-22м3 на Київщину наразі не поширюється", M
        ).target_count
        is None
    )
    # A time, and a decimal — neither is a group of targets.
    assert parse_message("Відбій о 3:00 на Славутич", M).target_count is None
    assert parse_message("3.5 на Славутич", M).target_count is None


def test_count_on_a_moving_number():
    # Real messages. The verb is the anchor: the place can be several words away
    # ("3 долітають до Броварів") or absent entirely ("Ще 4 летить"), so the
    # place-anchored form can't reach these.
    assert parse_message("Знову 3 долітають до Броварів і нові на Чернігівщині", M).target_count == 3
    assert parse_message("Ще 4 летить", M).target_count == 4
    assert parse_message("З Чернігівщини ще штук 5 летить", M).target_count == 5


def test_count_verb_form_is_present_tense_only():
    # The past tense is the voice of recaps and news, where the number is a
    # whole-night salvo total rather than a group over one district — stamping one
    # of those on a track is what once inflated the journal. Phrased without a
    # target noun on purpose: "30 ракет" would be counted by the older noun form,
    # which is not what this test is about.
    assert parse_message("Вночі всі 30 летіли на Київ", M).target_count is None
    assert parse_message("За ніч 12 пройшли повз Бровари", M).target_count is None


def test_count_near_a_place():
    # "біля"/"до" + a known place, also real messages.
    assert parse_message("Київ наче чисто, 2 біля Броварів", M).target_count == 2
    assert parse_message("Візуально 1 біля Обухова", M).target_count == 1
    # A date range must not read as a count: nothing known follows "26 до".
    assert parse_message("Із 26 до 29 липня буде обмежено рух", M).target_count is None


def test_bare_count_keeps_the_largest_stated_group():
    # Real message: several groups in one text. The count annotates ONE track, so
    # the largest stated group wins — the same rule the noun form already used,
    # and the per-district enumeration path still refuses to stamp it (handlers).
    r = parse_message("6 БпЛА на Вишгород, 2 на Згурівку. По 1 на Бориспіль, Бровари.", M)
    assert r.target_count == 6


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
        "🚀Найближчі 24 години: існує загроза масованої ракетної атаки. За даними "
        "моніторів, ворог може застосувати до 100 ракет. Для Києва серед імовірних "
        "напрямків називають Дарницький, Солом'янський райони, Видубичі, Березняки",
        "❗️Спостерігаю підвезення нових ракет в Брянську область. Загальна "
        "кількість, готова до застосування по Києву та області — більше 35 ракет.",
        "Маю інформацію, що на території Брянської та Курської областей може "
        "перебувати до 35 балістичних ракет. Можливі райони підвищеного ризику: "
        "Лук'янівка; Шулявка; Оболонь і Петрівка; Жуляни.",
    ]:
        r = parse_message(txt, M)
        assert r.negated, txt
        assert r.districts == [], txt
        assert not r.matched, txt


def test_official_after_action_recap_is_summary_not_impact():
    # An official ПС after-action bulletin ("Близько 11:30 ворог завдав удару …
    # інші дві влучили в Бучанському районі, – повідомили у ПС") names a raion +
    # "влучили", so it parsed as a fresh impact hours late. It's a retrospective
    # recap → routed as a summary (dispatch precedes the impact handler), so it
    # surfaces as a feed notice, not a live map strike.
    r = parse_message(
        "❗️Близько 11:30 ворог завдав удару по Київщині трьома балістичними "
        "ракетами Іскандер-М/С-400 з північного напрямку, – повідомили у ПС. "
        "Силам ППО вдалось перехопити 1 ракету, інші дві влучили в Бучанському районі.", M)
    assert r.summary


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


def test_bare_city_callout_is_citywide():
    # 08-04 (raw 4511): "Київ!!" one second before "Балістика!!" was dropped as
    # chatter. Bare city callout = city-level twin of a bare district callout.
    for txt in ["Київ!!", "Київ!", "Київ", "Столиця!"]:
        r = parse_message(txt, M)
        assert r.citywide and r.matched and r.districts == [], txt


def test_bare_city_rule_is_anchored_to_the_whole_message():
    # The anchor is what keeps it safe: merely naming the city is not a threat.
    for txt in ["Новини по Києву за добу", "Слава Києву!",
                "У Києві чути вибухи", "Київ - 3 цілі"]:
        assert not _CITYWIDE_BARE_RE.match(txt.lower()), txt


def test_over_the_city_is_citywide():
    # 08-04 (raw 4781): three drones over Kyiv, dropped because _CITYWIDE_STRONG
    # had "на місто" but not "над містом".
    r = parse_message("Вже 3х перших у вас над містом!", M)
    assert r.citywide and r.matched and r.districts == []


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


def test_standdown_that_announces_more_targets_does_not_close_anything():
    # 08-04: «Поки чисто. Але ще виходи!» (raw 4558) closed 5 tracks, all 5 back
    # within 6 min. lost_signal unset -> the message becomes a no-op.
    for txt in ["Поки чисто. Але ще виходи!",
                "Почули. Чисто. Можливі ще цілі.",
                "Дорозвідка. Ще можливі цілі. Більше 24 було вже."]:
        assert not parse_message(txt, M).lost_signal, txt
    # An unqualified stand-down is unchanged — it still closes.
    for txt in ["Чисто", "Вже чисто", "Дорозвідка"]:
        assert parse_message(txt, M).lost_signal, txt


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


def test_pulse_scoped_to_another_oblast_does_not_pulse():
    # Live 2026-08-01: "Ціль на Сумщині" is exactly pulse-shaped (3 words,
    # "ціль", no Kyiv district), so it corroborated the OPEN Kyiv city-wide
    # track and pushed its confidence to 0.7 — a Sumy sighting on a Kyiv card.
    for txt in ("Ціль на Сумщині", "Ціль Сумщина!", "Цілі на Чернігівщині"):
        assert not parse_message(txt, M).target_pulse, txt
    # An ORIGIN mention is the opposite case — that target is heading here.
    assert parse_message("Ціль з Курщини", M).target_pulse
    assert parse_message("Ціль!", M).target_pulse


def test_vinnytsia_oblast_spelling_variants_are_elsewhere():
    # 08-04 (raw 4693): only the adjective stem "вінницьк" was listed, so this
    # stayed pulse-shaped and corroborated the open Kyiv city-wide track.
    for txt in ("Ціль на Вінниччину", "Ціль на Вінничину"):
        assert not parse_message(txt, M).target_pulse, txt


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


def test_recon_analysis_writeup_is_suppressed():
    # An intelligence write-up about enemy scouting patterns names raions (the
    # recon FOCUS, not sightings) and mentions "крилатих ракет" — left alone it
    # raised phantom per-raion missile tracks AND seeded a false `missile` type
    # that bled onto the incident's typeless callouts (07-31 incident 153).
    r = parse_message(
        "Ворог здійснив чергову серію розвідувальних заходів у нашому регіоні. "
        "У фокусі противника опинилися Фастівський район, а також Вишгород. "
        "Ймовірно, ці дії пов’язані з опрацюванням можливих маршрутів для "
        "застосування БпЛА та крилатих ракет.",
        M,
    )
    assert r.negated and not r.matched
    assert not r.districts
    # A terse real callout with the same weapon word must still be a live target.
    assert parse_message("Крилаті ракети курсом на Київ", M).matched


def test_southern_corridor_gazetteer_gaps():
    # 2026-07-31 feed gaps — each was lost as "без району"/"не про загрозу".
    assert BY_EN["Khodosivka"] in {h.district_id for h in parse_message("На Ходосівку", M).districts}
    assert BY_EN["KonchaZaspa"] in {h.district_id for h in parse_message("Конча-Заспа шахед", M).districts}
    assert BY_EN["Rohoziv"] in {h.district_id for h in parse_message("Рогозів район 🔴.", M).districts}
    assert BY_EN["Pyrohiv"] in {h.district_id for h in parse_message("Шахед на Пирогів", M).districts}
    assert BY_EN["Chapaivka"] in {h.district_id for h in parse_message("БпЛА на Чапаївку", M).districts}
    assert BY_EN["VitaPoshtova"] in {h.district_id for h in parse_message("Ціль на Віта-Поштова", M).districts}
    # Bare "Заспа"/"Віта" must NOT match (collide with заспокойтесь/вітаю).
    assert not parse_message("Заспокойтесь, все тихо", M).districts
    assert not parse_message("Вітаю всіх на каналі", M).districts


def test_relayed_news_of_a_faraway_destruction_is_not_a_stand_down():
    # 2026-08-14 raw 6097: a news repost about a train destroyed in Siberia
    # carries "знищ" -> status=destroyed, and a destroyed message with no
    # district adopts whichever track is open. It closed T3332 (a live Шахед
    # over Київське водосховище, 14 min old) as «знищено».
    r = parse_message(
        "Повідомляють про знищення в Сибіру ешелону з північнокорейськими ракетами\n\n"
        "За попередніми даними, залізничний склад із балістичними ракетами КНДР "
        "знищили за 6 тисяч км від України.",
        M,
    )
    assert r.status == "destroyed"
    assert r.reportage and not r.matched


def test_reportage_marker_does_not_touch_a_localized_callout():
    # Both real reportage-marked sightings in the corpus name a raion — the
    # no-district gate is what keeps first-hand callouts alive.
    r = parse_message("Гатне повідомляють про приліт", M)
    assert not r.reportage and r.matched and r.districts
    r = parse_message(
        "🔴Кияни та жителі області будьте уважні! У районі Ворзеля, Ірпеня та Бучі "
        "зафіксовано ворожий розвідувальний БпЛА. За попередніми даними, ціль "
        "рухається у напрямку Києва.",
        M,
    )
    assert not r.reportage and r.matched and r.districts


def test_reportage_gate_leaves_a_real_minus_alone():
    # A spotter's own stand-down carries no reportage marker and must still
    # close its track, however long the message is.
    for txt in ["Мінус", "Тут мінус. Фіксується 1х в район Чорнобиля з Чернігівщини.",
                "Мінус останній. Локацяйно чисто. Але до відбою увага, їх було "
                "більше, ніж 4х загалом, йшли низько дуже по Дніпру."]:
        r = parse_message(txt, M)
        assert r.status == "destroyed" and not r.reportage, txt


def test_analytic_past_frame_does_not_raise_a_city_alert():
    # 2026-08-15 raw 6145: analysis of an EARLIER attack. "на київ" inside the
    # past clause "атаки, що була на Київ" raised a live city-wide ballistic
    # threat at 23:09 with nothing in the sky.
    r = parse_message(
        "Висновок ще в тому, що рф економить «Іскандери-М», а використовує "
        "союзницькі «KN-23», а також попередньої атаки, що була на Київ, ворог "
        "також в основному застосував ракети ЗРК.",
        M,
    )
    assert r.summary
    assert not r.citywide and not r.matched


def test_past_passive_city_attack_is_a_summary_not_a_live_notice():
    # 2026-08-15 raw 6143: rules found no district, so it reached the LLM, which
    # read it as citywide and rescued it into a LIVE citywide notice. As a
    # summary it stays info-only AND should_fallback stops paying for the call.
    from app.pipeline.ingest.resolve import should_fallback

    r = parse_message("Місто було атаковане після атаки БПЛА, зокрема реактивними.", M)
    assert r.summary and not r.citywide and not r.matched
    assert not should_fallback(r)
    # Present-tense city callouts must still raise the live alert.
    assert parse_message("Ціль на місто!", M).citywide


def test_koncha_zaspa_matches_the_unhyphenated_spelling():
    # 2026-08-16 raw 6278/6237: the entry was keyed on the hyphenated stem only,
    # and _stem() strips spaces, so a multiword alias could never match spaced
    # text. Both spellings must resolve to the same place.
    for txt in ["Конча-Заспа шахед", "Конча Заспа", "Конча заспа",
                "1х реактив повз Конча-Заспа у напрямку Києва."]:
        assert BY_EN["KonchaZaspa"] in {h.district_id for h in parse_message(txt, M).districts}, txt
    # Bare "Заспа" stays out (its stem collides with заспокоїтись).
    assert not parse_message("Заспокоїтись треба, все тихо", M).districts


def test_northern_approach_gazetteer_gaps():
    # 2026-08-17 feed gaps on the Belarus->exclusion-zone corridor.
    assert BY_EN["Strakholissia"] in {
        h.district_id for h in parse_message("Страхолісся два кружляють", M).districts}
    for txt in ["2 в ЧЗВ", "З Білорусі на ЧЗВ", "Їх три, летять на ЧЗВ",
                "через ЧЗВ пара на захід йде",
                "Тут мінус. Фіксується 1х в район Чорнобиля з Чернігівщини."]:
        assert BY_EN["ChornobylZone"] in {
            h.district_id for h in parse_message(txt, M).districts}, txt


def test_short_whole_word_alias_cannot_match_inside_a_word():
    # "чзв" is below the 4-char stem floor and only matches as a whole word, so
    # it can never fire on a longer token the way a stem would.
    assert not parse_message("чзвабра кадабра", M).districts
    assert not parse_message("Ачзв", M).districts


def test_over_kyiv_is_citywide_but_a_rainbow_is_not():
    # raw 4824 "4 БпЛА над Києвом" produced nothing at all: "над містом" was a
    # city phrase, "над Києвом" wasn't. It is WEAK, not strong — the corpus's
    # only other uses of the phrase are «🌈 Над Києвом зʼявилася веселка».
    for txt in ["4 БпЛА над Києвом", "Балістика над столицею"]:
        r = parse_message(txt, M)
        assert r.citywide and r.matched and r.districts == [], txt
    for txt in ["🌈 Над Києвом цього вечора зʼявилася яскрава веселка",
                "🌈Подвійна веселка зʼявилась над столицею."]:
        r = parse_message(txt, M)
        assert not r.citywide and not r.matched, txt


def test_threat_level_bulletin_becomes_a_forecast_or_status_notice():
    # The standing "по балістиці" side-channel: 51 such messages in the captured
    # corpus, each one previously silent AND paying for an LLM call.
    for txt in ["Сьогодні теж червоний рівень по балістиці, реагуємо на тривоги",
                "Отримано червоний сигнал щодо загрози обстрілу балістикою протягом двох діб!",
                "🟣 Загроза БАЛІСТИКИ", "По балістиці загроза зберігається."]:
        r = parse_message(txt, M)
        assert r.notice_kind == "forecast", txt
    for txt in ["По балістиці тихо на даний момент.", "Балістики поки не видно",
                "Пусків Цирконів наразі немає.",
                "Наразі без запусків аеробалістичної ракети типу «Кинджал»."]:
        r = parse_message(txt, M)
        assert r.notice_kind == "status", txt


def test_threat_level_bulletin_never_localizes_or_stands_down():
    # A level bulletin is feed context only: no district, no track, and above all
    # not an all-clear — a spotter's "тихо" must not close anything.
    r = parse_message("По балістиці тихо на даний момент.", M)
    assert r.districts == [] and not r.citywide and r.status != "clear"
    # A raion of its own always wins — that's a real sighting, not a bulletin.
    r = parse_message("Балістика на Троєщині, тихо не буде", M)
    assert r.notice_kind is None and names(r) == ["Троєщина"]
    # Someone else's bulletin stays someone else's.
    assert parse_message("По Чернігівщині поки тихо, балістики немає", M).notice_kind is None


def test_engagement_post_is_promo():
    # One channel runs a fundraiser scoreboard with no link and no card number;
    # the identical text appeared 8 times in one 5000-message window, each time
    # reaching the LLM as an unlocalized "threat".
    for txt in ["🇺🇦🔴На жаль , підтримало збір тільки 4ро людей!!! Дякуємо тим хто не пройде повз",
                "🔴Доречі поки чекаємо відбій, дивитесь футбол?",
                "🔴Скільки Киян сьогодні буде зі мною протягом ночі? Дайте реакцію щоб я бачив"]:
        r = parse_message(txt, M)
        assert r.promo and not r.matched, txt


def test_spotter_shorthand_resolves_to_its_area():
    # The «Місто Кия» shorthand, decoded by the maintainer from the coverage-gap
    # export: five callout forms that used to localize nowhere.
    cases = {
        "ПОХ 🔴.": "Позняки-Осокорки-Харківський",
        "На ПОХ йде новий реактивний 🔴.": "Позняки-Осокорки-Харківський",
        "Пуща 🔴.": "Пуща-Водиця",
        "Шахед над Пущею-Водицею": "Пуща-Водиця",
        "Голос 🔴.": "Голосіївський",
        "Голос парк 🔴.": "Голосіївський",
        "Торгмаш 🔴.": "Бровари",
    }
    for txt, expected in cases.items():
        assert expected in names(parse_message(txt, M)), txt


def test_shorthand_aliases_do_not_fire_inside_everyday_words():
    # Each of these appears in the real corpus; every one of them would have
    # been a phantom target if the aliases matched as plain stems.
    for txt in ["🌧 Київ готується до нової хвилі похолодання",
                "Хутко всі поховались, будьте обережні",
                "Ці БПЛА походу проводять розвідку передмістя",
                "🫶Велике прохання, проголосуйте за наш канал",
                "Тривогу вчасно не оголосили",
                "Пущено 12 ракет", "Усього було запущено 41 ракету"]:
        assert names(parse_message(txt, M)) == [], txt


def test_holos_kyeva_is_a_channel_not_holosiivskyi():
    # "Голос Києва — @golos_kieva попередив про загрозу" quotes another channel.
    r = parse_message("Під час минулої атаки Голос Києва — @golos_kieva попередив "
                      "про загрозу одним із перших.", M)
    assert names(r) == []


def test_utility_and_city_services_news_naming_a_neighbourhood_is_suppressed():
    # Both real, both raised a track once their neighbourhood entered the
    # gazetteer: scheduled plumbing works and a beach water-quality bulletin.
    for txt in [
        "У житловому масиві Пуща-Водиця сьогодні з 23:00 і до 6:00 під час виконання "
        "ремонтних робіт можливе зниження тиску у водопостачанні",
        "🏖 На більшості пляжів Києва вода відповідає нормам. Безпечною воду визнали "
        "на 13 пляжах і водоймах столиці, зокрема у Пущі-Водиці",
    ]:
        r = parse_message(txt, M)
        assert r.civic_notice and not r.matched, txt


def test_southern_staging_ring_localizes():
    # The southern approach towns from the coverage-gap export: targets loiter
    # and turn over these before entering the city.
    cases = {
        "2 Реактивних БпЛА на Березань.": ["Березань"],
        "Один на Білу Церкву": ["Біла Церква"],
        "Рокитне/БЦ уважно по двох групах БПЛА.": ["Рокитне", "Біла Церква"],
        "1 шахед на Кагарлик": ["Кагарлик"],
        "Райони Миронівки/Таращі/Богуслава уважно по третьому ланцюгу БПЛА.":
            ["Миронівка", "Тараща", "Богуслав"],
        "Кийлів район. Фіксується один, другий зник.": ["Кийлів"],
        "Розвернувся у район БЦ 🔴.": ["Біла Церква"],
    }
    for txt, expected in cases.items():
        assert sorted(names(parse_message(txt, M))) == sorted(expected), txt


def test_tserkva_only_counts_inside_bila_tserkva():
    # "церкв" is the only matchable word of the spaced name, so it is gated on a
    # preceding "Біл…" — otherwise a strike report pins a town 80 km south.
    assert names(parse_message("У Білій Церкві фіксується БпЛА", M)) == ["Біла Церква"]
    assert names(parse_message("Приліт у церкву, є руйнування", M)) == []
    assert names(parse_message("Пошкоджено церкву та кілька будинків", M)) == []


def test_oblast_scope_report_is_a_notice_not_a_track():
    # "Тривога в області" is the heads-up half (forecast); a count with no raion
    # is the state half (status). Neither can go on the map.
    assert parse_message("Тривога в області, загроза БПЛА", M).notice_kind == "forecast"
    for txt in ["По області 2-3 БПЛА", "В області цей один.", "Залишився один в області"]:
        r = parse_message(txt, M)
        assert r.notice_kind == "status" and r.districts == [], txt
    # A raion of its own always wins — that IS a placeable target.
    r = parse_message("Бориспіль південь 🔴. Він останній в області.", M)
    assert r.notice_kind is None and names(r) == ["Бориспіль"]


def test_salvo_scale_without_a_place_is_a_notice():
    # During a salvo the count IS the situation, and it used to vanish entirely.
    for txt in ["До 6 ракет вже.", "Вже близько 21 ракет пустили", "Був залп з 5 ракет!",
                "Десь під 40 ракет …"]:
        r = parse_message(txt, M)
        assert r.notice_kind == "status" and r.districts == [], txt


def test_city_bound_callout_is_an_alert_not_a_notice():
    # "в бік Столиці" / "в напрямку Столиці" carry a count too, but they say
    # where it is going — that outranks the scale notice.
    for txt in ["❗️Локаційно фіксується до 10х ворожих БпЛА в бік Столиці.",
                "‼️~10х крилатих ракет в напрямку Столиці."]:
        r = parse_message(txt, M)
        assert r.citywide and r.notice_kind is None, txt

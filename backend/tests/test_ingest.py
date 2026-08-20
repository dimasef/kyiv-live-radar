"""Unit tests for the rule -> LLM fallback routing decision."""

from datetime import datetime, timedelta

from app.domain.origins import target_elsewhere
from app.gazetteer import DISTRICTS
from app.parsing import DistrictMatcher, parse_message
from app.parsing.matcher import normalize
from app.pipeline.ingest import _note_and_inherit_type, should_fallback

M = DistrictMatcher([{"id": i + 1, **d} for i, d in enumerate(DISTRICTS)])


def test_should_fallback_for_unlocalized_kyiv_relevant_message():
    r = parse_message("Увага, реактивний йде на зниження у районі!", M)
    assert should_fallback(r)


def test_should_not_fallback_when_target_is_in_another_oblast():
    # A target whose LOCATION is a whole REGION with no settlement named — the
    # LLM cannot recover a place that isn't in the text, so the call would be
    # pure spend. True for someone else's oblast ("на Дніпро") AND for the
    # watched north ("на Чернігівщині"): watching a region doesn't conjure a
    # settlement out of a message that names none.
    for txt in [
        "Знову 2х реактивних БПЛА на Чернігівщині, вектор такий самий.",
        "Шахед на Чернігівщині",
        "Ціль на Дніпро.",
        # Origin here, but the TARGET is Dnipropetrovshchyna — still elsewhere.
        "БПЛА з Чернігівщини курсом на Дніпропетровщину.",
    ]:
        r = parse_message(txt, M)
        assert not should_fallback(r), txt


def test_an_unknown_village_in_a_watched_region_still_reaches_the_llm():
    """The counterpart of the rule above: a place we simply don't have in the
    gazetteer yet names no oblast, so it is exactly the case the LLM enum
    exists for — suppressing it would freeze northern coverage at whatever the
    gazetteer happened to contain."""
    assert should_fallback(parse_message("Реактивний на Пакуль", M))


def test_inbound_from_another_oblast_is_a_directional_axis():
    # An INBOUND target whose ORIGIN is a curated other-oblast launch zone
    # ("з Брянщини"/"з Чернігівщини"/"з району Ростова", heading toward Kyiv) is
    # now detected DETERMINISTICALLY by rules as a directional axis — no wasted
    # LLM call. (Previously it reached the triage LLM, which couldn't localize a
    # non-gazetteer origin anyway.)
    for txt in [
        "Тим часом, ворог запустив ще пару реактивних БПЛА з Брянщини.",
        "4х БПЛА реактивних йшло з Чернігівщини, зараз фіксується лише пара.",
        "З району Ростова ворог здійснив запуск реактивних БПЛА.",
    ]:
        r = parse_message(txt, M)
        assert r.directional, txt
        assert r.origin_key is not None, txt
        assert not should_fallback(r), txt  # rules handle it -> no LLM fallback


def test_citywide_message_does_not_trigger_llm_fallback():
    # A city-wide threat ("Балістика на Київ") has no raion for the LLM to find —
    # it must NOT pay for a guaranteed-empty fallback call. Stage C both handles
    # it AND removes this wasted call.
    for txt in ["Балістика на Київ", "Ракетна небезпека по Києву", "Ціль на місто!"]:
        r = parse_message(txt, M)
        assert r.citywide
        assert not should_fallback(r), txt


def test_donation_ad_does_not_trigger_llm_fallback():
    # A donation/ad post (monobank link + bare card number) is flagged promo by
    # rules and must NEVER reach the LLM — it's definitionally not a target, and
    # a fallback call just burns budget (real case: a "підтримати проект на каву"
    # post cost a Haiku call before this gate).
    for txt in [
        "Підтримати проект на каву:\nhttps://send.monobank.ua/jar/2EDJBw6Bv1\n4874100038678838\nДонати тримають проект на плаву!",
        "Створив ракетний канал, підписуйтесь: https://t.me/somechannel",
    ]:
        r = parse_message(txt, M)
        assert r.promo, txt
        assert not should_fallback(r), txt


def test_other_oblast_mention_does_not_hide_a_real_kyiv_district():
    # If a real Kyiv-area district WAS rule-matched, the early "districts
    # non-empty" check already wins — the other-oblast wording elsewhere in
    # the same message must not suppress it.
    r = parse_message("З Чернігівщини курсом на Дарницький район.", M)
    assert r.districts != []
    assert not should_fallback(r)  # already localized by rules, no LLM needed


# --- Cross-message target-type inheritance (per channel) ---

T0 = datetime(2026, 7, 11, 0, 52)  # UTC (03:52 Kyiv), like the real ballistic night


def _feed(text, source_id, when):
    """Parse a message and run the ingest-level type-inheritance step on it."""
    r = parse_message(text, M)
    _note_and_inherit_type(r, source_id, when)
    return r


def test_bare_toponym_inherits_recent_ballistic_type_same_channel():
    # The real 03:52-03:54 sequence: type stated once, then bare toponyms.
    _feed("Балістика!", source_id=1, when=T0)
    troya = _feed("Троя", source_id=1, when=T0 + timedelta(minutes=1))
    vyshneve = _feed("Вишневе", source_id=1, when=T0 + timedelta(minutes=2))
    assert [h.district_id for h in troya.districts]  # localized
    assert troya.target_type == "ballistic"
    assert vyshneve.target_type == "ballistic"


def test_no_inheritance_across_different_channels():
    _feed("Балістика!", source_id=1, when=T0)
    other = _feed("Троя", source_id=2, when=T0 + timedelta(minutes=1))
    assert other.target_type == "unknown"  # different channel, no context


def test_inheritance_expires_after_window():
    _feed("Балістика!", source_id=1, when=T0)
    late = _feed("Троя", source_id=1, when=T0 + timedelta(minutes=30))
    assert late.target_type == "unknown"  # stale context is not inherited


def test_citywide_message_inherits_type():
    # A city-wide callout ("Ціль на місто!") is a real sighting — it inherits the
    # recent channel type, so a blind ballistic phase reads as a ballistic alert.
    _feed("Балістика!", source_id=1, when=T0)
    r = _feed("Ціль на місто!", source_id=1, when=T0 + timedelta(minutes=1))
    assert r.citywide and r.target_type == "ballistic"


def test_carrier_activity_does_not_become_the_channel_type():
    # Live 2026-08-19 21:11: bombers left Olenya (four hours from their launch
    # lines) WHILE a ballistic salvo was overhead. The carrier post types itself
    # `missile` so it can surface as a forecast notice, but claiming the channel
    # is now calling cruise missiles would retype the very next bare toponym —
    # which belonged to the salvo.
    carrier = _feed("З оленя злетіли тушки", source_id=1, when=T0)
    assert carrier.target_type == "missile"  # for its own notice
    obukhiv = _feed("Обухів", source_id=1, when=T0 + timedelta(seconds=75))
    assert obukhiv.target_type == "unknown"  # context untouched by the carrier
    # A launch report that names the weapon is a different matter: those missiles
    # ARE in the air, so it sets the context like any other typed callout.
    _feed("Пуски крилатих ракет із ТУшок", source_id=2, when=T0)
    r = _feed("Обухів", source_id=2, when=T0 + timedelta(seconds=75))
    assert r.target_type == "missile"


def test_non_sighting_message_does_not_inherit():
    # Neither a district nor a city-wide sighting (a chat aside) — there is
    # nothing to attach a type to, so it stays unknown.
    _feed("Балістика!", source_id=1, when=T0)
    r = _feed("Як ви?", source_id=1, when=T0 + timedelta(minutes=1))
    assert not r.districts and not r.citywide
    assert r.target_type == "unknown"


def test_stated_type_is_never_overridden_by_context():
    _feed("Балістика!", source_id=1, when=T0)
    shahed = _feed("Шахед на Троєщину", source_id=1, when=T0 + timedelta(minutes=1))
    assert shahed.target_type == "shahed"  # its own stated type wins


def test_anticipated_wave_does_not_become_the_channel_type():
    # Live 2026-08-19 22:18-22:20. Kalibrs were fifteen minutes from Kyiv when
    # both channels posted about a possible NEXT ballistic wave; every cruise
    # callout that followed inherited «балістика» from those two posts. A
    # forecast about what MIGHT come cannot relabel what is already in the sky.
    _feed("Калібри йдуть в бік Київщини", source_id=1, when=T0)
    ahead = _feed("Найближчим часом можлива повторна хвиля балістики. Пильнуємо.",
                  source_id=1, when=T0 + timedelta(minutes=1))
    assert ahead.notice_kind == "forecast" and ahead.anticipated
    boguslav = _feed("Богуслав/Миронівка 🔴.", source_id=1, when=T0 + timedelta(minutes=2))
    assert boguslav.target_type == "missile"  # still the cruise wave, not ballistic


def test_a_named_cruise_weapon_corrects_a_ballistic_context():
    # Same night, 22:22: both channels said «Калібри» while the context was
    # stale-ballistic, and both stayed ballistic — the downgrade guard could not
    # tell a named cruise weapon from a bare "ракети". It has to, because that
    # is the spotter identifying what is flying.
    _feed("Балістика!", source_id=1, when=T0)
    _feed("6 калібрів звернули на Черкащину", source_id=1, when=T0 + timedelta(minutes=1))
    obukhiv = _feed("Обухів", source_id=1, when=T0 + timedelta(minutes=2))
    assert obukhiv.target_type == "missile"


def test_generic_missile_mention_does_not_downgrade_ballistic_context():
    # The real tonight sequence: a bare "3 ракети" fell between the toponym
    # callouts of a С-400 salvo. It must NOT downgrade the ballistic context —
    # the later toponyms should still inherit ballistic, not generic missile.
    _feed("Балістика!", source_id=1, when=T0)
    _feed("3 ракети", source_id=1, when=T0 + timedelta(minutes=1))
    vyshneve = _feed("Вишневе", source_id=1, when=T0 + timedelta(minutes=2))
    assert vyshneve.target_type == "ballistic"


def test_specific_ballistic_still_overrides_a_generic_missile_context():
    # The reverse direction is a real change and must take effect: a generic
    # missile context followed by an explicit ballistic marker upgrades.
    _feed("Крилата ракета", source_id=1, when=T0)  # missile (cruise)
    _feed("Балістика!", source_id=1, when=T0 + timedelta(minutes=1))
    troya = _feed("Троя", source_id=1, when=T0 + timedelta(minutes=2))
    assert troya.target_type == "ballistic"


def test_negated_type_aside_does_not_poison_context():
    # The real 07-18 sequence: a spotter aside containing "це не БПЛА" typed
    # itself shahed, and "Увага на Київ!" 22 seconds later inherited it — the
    # main city-wide card of a ballistic salvo was labeled БПЛА for 15 minutes.
    _feed("Балістика!", source_id=1, when=T0)
    _feed("Воно з лівого на правий за кілька секунд, це не БПЛА. "
          "Тому весь Київ уважно.", source_id=1, when=T0 + timedelta(minutes=1))
    r = _feed("Увага на Київ!", source_id=1, when=T0 + timedelta(minutes=2))
    assert r.citywide and r.target_type == "ballistic"


def test_donation_post_does_not_update_type_context():
    # A donation post's sign-off mentions types without being about a target —
    # it must neither set nor overwrite the channel context.
    _feed("Адмінам на енергетик за працю. Моно - 4441111126308174. "
          "Будемо працювати до останнього Шахеда та ракети",
          source_id=1, when=T0)
    r = _feed("Троя", source_id=1, when=T0 + timedelta(minutes=1))
    assert r.target_type == "unknown"


def test_buzz_slang_chatter_does_not_poison_type_context():
    # The real 07-24 sequence: a reassurance aside "там реактивні бджілки" typed
    # itself jet_drone, and the citywide ballistic callout "На Київщину!" 26s
    # later inherited it — the main city card of a ballistic salvo stuck at БпЛА
    # (jet_drone never upgrades to the missile family). The buzz-slang aside is
    # parsed with a jet type but must NOT set the channel's live type context.
    aside = _feed("Кажу одразу, що там реактивні бджілки, але до відбою уважно",
                  source_id=1, when=T0)
    assert aside.chatter and aside.target_type == "jet_drone"
    r = _feed("На Київщину!", source_id=1, when=T0 + timedelta(seconds=26))
    assert r.citywide and r.target_type == "unknown"  # not the poisoned jet_drone


def test_buzz_slang_does_not_overwrite_live_ballistic_context():
    # A buzz-slang aside carrying a jet keyword mid-salvo must not knock an
    # already-live ballistic context down to jet_drone.
    _feed("Балістика!", source_id=1, when=T0)
    _feed("там реактивні бджілки", source_id=1, when=T0 + timedelta(seconds=20))
    r = _feed("На Київщину!", source_id=1, when=T0 + timedelta(seconds=40))
    assert r.target_type == "ballistic"


def test_zircon_callout_updates_type_context():
    # "Циркон з курська" now types (ballistic) — the channel's later bare
    # toponyms inherit it instead of producing "unknown" tracks.
    _feed("Циркон з курська", source_id=1, when=T0)
    r = _feed("Троя", source_id=1, when=T0 + timedelta(minutes=1))
    assert r.target_type == "ballistic"


def test_newly_covered_target_oblasts_skip_the_llm():
    # A 5000-message coverage sweep: each of these named a target location the
    # elsewhere list didn't know, so every one of them paid for an LLM call that
    # came back empty. Prilyuky/Nizhyn/Cherkasy/Sumy/Odesa/Poland are not ours.
    for txt in [
        "Пара БПЛА на Прилуки",
        "Два Шахеди на Ніжин, реактивні",
        "Крилаті на Черкаси",
        "Ціль на Суми.",
        "Скоріш за все думали це Циркон, а це Онікс на Одесу!",
        "Ракета ввійшла в ПП Польщі.",
        "На Talmaza, Молдова - летіла російська ракета.",
        "Один курсом на Житомирську область",
    ]:
        r = parse_message(txt, M)
        assert not should_fallback(r), txt


def test_far_city_used_as_a_local_road_or_destination_stays_ours():
    # The collisions that trimmed the list: a highway named after a far city runs
    # through Kyivshchyna, and a message that states US as the destination is
    # exactly what this feed is for — neither is "someone else's threat".
    for txt in ["Шахед по трасі Київ-Суми.", "Шахед над Одеською трасою"]:
        assert should_fallback(parse_message(txt, M)), txt
    # Us as the stated destination outranks every other place named on the way.
    r = parse_message("Шахеди зі Сумщини пішли в район Ніжина, далі ймовірно на Київщину.", M)
    assert r.matched and not target_elsewhere(normalize(r.raw_text))


def test_level_bulletin_does_not_pay_for_an_llm_call():
    # It already became a feed notice — there is no district for the LLM to find.
    for txt in ["По балістиці тихо на даний момент.", "🟣 Загроза БАЛІСТИКИ"]:
        r = parse_message(txt, M)
        assert r.notice_kind and not should_fallback(r), txt

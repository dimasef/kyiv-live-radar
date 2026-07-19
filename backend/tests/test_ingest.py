"""Unit tests for the rule -> LLM fallback routing decision."""

from datetime import datetime, timedelta

from app.gazetteer import DISTRICTS
from app.parsing import DistrictMatcher, parse_message
from app.pipeline.ingest import _note_and_inherit_type, should_fallback

M = DistrictMatcher([{"id": i + 1, **d} for i, d in enumerate(DISTRICTS)])


def test_should_fallback_for_unlocalized_kyiv_relevant_message():
    r = parse_message("Увага, реактивний йде на зниження у районі!", M)
    assert should_fallback(r)


def test_should_not_fallback_when_target_is_in_another_oblast():
    # A target whose LOCATION is another oblast ("на Чернігівщині", "на Дніпро"),
    # with no Kyiv-area place named — an LLM call can't recover a Kyiv district
    # that isn't in the text, so it stays suppressed.
    for txt in [
        "Знову 2х реактивних БПЛА на Чернігівщині, вектор такий самий.",
        "Шахед на Чернігівщині",
        "Ціль на Дніпро.",
        # Origin here, but the TARGET is Dnipropetrovshchyna — still elsewhere.
        "БПЛА з Чернігівщини курсом на Дніпропетровщину.",
    ]:
        r = parse_message(txt, M)
        assert not should_fallback(r), txt


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


def test_zircon_callout_updates_type_context():
    # "Циркон з курська" now types (ballistic) — the channel's later bare
    # toponyms inherit it instead of producing "unknown" tracks.
    _feed("Циркон з курська", source_id=1, when=T0)
    r = _feed("Троя", source_id=1, when=T0 + timedelta(minutes=1))
    assert r.target_type == "ballistic"

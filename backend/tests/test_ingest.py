"""Unit tests for the rule -> LLM fallback routing decision."""

from app.gazetteer import DISTRICTS
from app.ingest import _should_fallback
from app.parser import DistrictMatcher, parse_message

M = DistrictMatcher([{"id": i + 1, **d} for i, d in enumerate(DISTRICTS)])


def test_should_fallback_for_unlocalized_kyiv_relevant_message():
    r = parse_message("Увага, реактивний йде на зниження у районі!", M)
    assert _should_fallback(r)


def test_should_not_fallback_when_only_another_oblast_is_named():
    # Real feed examples: a target only over/from another oblast, with no
    # Kyiv-area place named at all — an LLM call can't recover a Kyiv
    # district that was never mentioned in the text.
    for txt in [
        "Тим часом, ворог запустив ще пару реактивних БПЛА з Брянщини.",
        "Знову 2х реактивних БПЛА на Чернігівщині, вектор такий самий.",
        "Шахед на Чернігівщині",
    ]:
        r = parse_message(txt, M)
        assert not _should_fallback(r), txt


def test_other_oblast_mention_does_not_hide_a_real_kyiv_district():
    # If a real Kyiv-area district WAS rule-matched, the early "districts
    # non-empty" check already wins — the other-oblast wording elsewhere in
    # the same message must not suppress it.
    r = parse_message("З Чернігівщини курсом на Дарницький район.", M)
    assert r.districts != []
    assert not _should_fallback(r)  # already localized by rules, no LLM needed

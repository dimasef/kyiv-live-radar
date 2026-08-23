"""Prompt shape and the cost accounting that follows it.

The call itself is never made here — what these guard is that the two content
blocks still concatenate into exactly the prompt the single string used to
build, that the gazetteer really is absent by default (the whole point of
llm_localize_enabled: it was 81% of the tokens), and that a cached call is
PRICED as a cached call (the budget guard sums the very column this computes).
"""

from types import SimpleNamespace

import pytest

from app.config import settings
from app.domain.origins import ORIGIN_KEYS
from app.parsing.llm import (
    _LOCALIZED_NO_LIST,
    _LOCALIZED_WITH_LIST,
    _MESSAGE_BLOCK,
    _PROMPT,
    _content_blocks,
    _schema,
    _static_prompt,
    _system,
    _usage_from,
)
from app.parsing.matcher import DistrictMatcher

TEXT = "2 реактивні"


class _Row:
    """Minimal district stand-in for DistrictMatcher (id/name/aliases/region)."""

    def __init__(self, id_, name, region="kyiv"):
        self.id = id_
        self.name_uk = name
        self.name_en = name
        self.aliases = []
        self.region = region
        self.lat = 50.4
        self.lon = 30.5


@pytest.fixture
def matcher():
    return DistrictMatcher([_Row(1, "Голосіївський"), _Row(2, "Ніжин", "chernihiv")])


def _static(localize: bool = False) -> str:
    from app.parsing.llm import _static_prompt as build

    return build(DistrictMatcher([_Row(1, "Голосіївський")]), localize)[0]


def _usage(input_tokens=0, written=0, read=0, output=60):
    return SimpleNamespace(usage=SimpleNamespace(
        input_tokens=input_tokens, output_tokens=output,
        cache_creation_input_tokens=written, cache_read_input_tokens=read))


def test_blocks_concatenate_into_the_same_prompt_as_before():
    # The API joins content blocks with nothing between them, so the blank line
    # that used to precede "Message:" has to survive the split — otherwise the
    # model silently receives a different prompt than the one this was tuned on.
    blocks = _content_blocks(_static(), TEXT)
    assert "".join(b["text"] for b in blocks) == _static() + _MESSAGE_BLOCK.format(text=TEXT)
    assert blocks[-1]["text"].endswith(TEXT)  # the message is last: the rest is a prefix


def test_no_gazetteer_in_the_prompt_by_default(matcher):
    # The measured saving: the listing was 6 139 of 7 597 prompt tokens. If a
    # refactor ever puts it back unconditionally, the bill silently multiplies.
    static, id_enum = _static_prompt(matcher, localize=False)
    assert id_enum is None
    assert "Голосіївський" not in static and "Ніжин" not in static
    assert "Known districts" not in static
    assert _LOCALIZED_NO_LIST in static
    # The listing is the ONLY thing that goes: origins, types, statuses and the
    # triage taxonomy all still have to be there.
    assert ORIGIN_KEYS[0] in static and "jet_drone" in static and "directional" in static


def test_listing_comes_back_when_localization_is_on(matcher):
    static, id_enum = _static_prompt(matcher, localize=True)
    assert id_enum == [1, 2]
    assert "1: Голосіївський [Київщина]" in static
    assert "2: Ніжин [Чернігівщина]" in static  # region tag disambiguates cross-border names
    assert _LOCALIZED_WITH_LIST in static


def test_schema_only_asks_for_districts_when_it_has_an_enum():
    # An empty enum would be an unsatisfiable constraint, and asking for a field
    # the prompt gives no way to fill invites the model to invent one.
    without = _schema(None)
    assert "district_ids" not in without["properties"]
    assert "district_ids" not in without["required"]
    with_list = _schema([1, 2])
    assert with_list["properties"]["district_ids"]["items"]["enum"] == [1, 2]
    assert "district_ids" in with_list["required"]


def test_system_prompt_drops_the_district_rails_with_the_listing():
    assert "Return ONLY districts from the provided list" in _system(True)
    assert "Return ONLY districts from the provided list" not in _system(False)
    # The out-of-scope rule is about geography, not about the list — it has to
    # survive, or a target 'на Дніпро' reads as a Kyiv sighting.
    assert "Дніпро" in _system(False)


def test_cache_breakpoint_sits_on_the_static_block_only(monkeypatch):
    monkeypatch.setattr(settings, "llm_cache_ttl", "1h")
    blocks = _content_blocks(_static(), TEXT)
    assert blocks[0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert "cache_control" not in blocks[1]  # caching the message would defeat the point


def test_caching_is_off_by_default():
    # Haiku 4.5 will not cache a prefix under 4096 tokens, and without the
    # listing this prompt is ~1.5k — asking anyway bought nothing and, once the
    # gazetteer briefly pushed it over the line, cost 2x per call in writes
    # nobody ever read back (measured 2.02 $/MTok on 2026-08-22).
    assert settings.llm_cache_ttl == ""
    blocks = _content_blocks(_static(), TEXT)
    assert all("cache_control" not in b for b in blocks)
    assert "".join(b["text"] for b in blocks) == _static() + _MESSAGE_BLOCK.format(text=TEXT)


def test_every_named_jet_model_is_in_the_prompt():
    """Drift guard between the rules' vocabulary and the prompt. The verdict's
    type stamps every notice and axis it produces (and the whole verdict when a
    district is recovered), so a model the rules type as jet_drone and the
    prompt never mentions comes back as `missile` — the generic word around it
    («10 ракет Бандероль») is exactly what the model would otherwise go by."""
    from app.parsing.vocab import _JET_MODEL

    prompt = _PROMPT.lower()
    for stem in _JET_MODEL:
        assert stem in prompt, stem


def test_a_cache_read_is_priced_as_a_cache_read(monkeypatch):
    monkeypatch.setattr(settings, "llm_cache_ttl", "1h")
    # 5900 tokens read from cache + 5 fresh: a tenth of the input price, not the
    # $0.006 an uncached call of the same size costs.
    usage = _usage_from(_usage(input_tokens=5, read=5900))
    assert usage.input_tokens == 5905  # reported whole, so /raw stays comparable
    assert usage.cost_usd == round((5 + 5900 * 0.10) / 1e6 * 1.00 + 60 / 1e6 * 5.00, 6)
    assert usage.cost_usd < 0.001


def test_a_cache_write_is_priced_at_the_1h_multiplier(monkeypatch):
    monkeypatch.setattr(settings, "llm_cache_ttl", "1h")
    usage = _usage_from(_usage(input_tokens=5, written=5900))
    assert usage.cost_usd == round((5 + 5900 * 2.00) / 1e6 * 1.00 + 60 / 1e6 * 5.00, 6)


def test_an_uncached_call_prices_exactly_as_before(monkeypatch):
    monkeypatch.setattr(settings, "llm_cache_ttl", "")
    usage = _usage_from(_usage(input_tokens=5953))
    assert usage.input_tokens == 5953
    assert usage.cost_usd == round(5953 / 1e6 * 1.00 + 60 / 1e6 * 5.00, 6)

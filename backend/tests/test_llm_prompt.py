"""Prompt caching: the request shape and the cost accounting that follows it.

The call itself is never made here — what these guard is that the two content
blocks still concatenate into exactly the prompt the single string used to
build, and that a cached call is PRICED as a cached call (the budget guard sums
the very column this computes).
"""

from types import SimpleNamespace

from app.config import settings
from app.domain.origins import ORIGIN_KEYS
from app.parsing.llm import _MESSAGE_BLOCK, _PROMPT, _content_blocks, _usage_from

LISTING = "1: Голосіївський [Київщина]\n2: Ніжин [Чернігівщина]"
TEXT = "2 реактивні"


def _static() -> str:
    return _PROMPT.format(listing=LISTING, origins=", ".join(ORIGIN_KEYS))


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


def test_cache_breakpoint_sits_on_the_static_block_only():
    blocks = _content_blocks(_static(), TEXT)
    assert blocks[0]["cache_control"] == {"type": "ephemeral", "ttl": settings.llm_cache_ttl}
    assert "cache_control" not in blocks[1]  # caching the message would defeat the point


def test_caching_can_be_turned_off(monkeypatch):
    monkeypatch.setattr(settings, "llm_cache_ttl", "")
    blocks = _content_blocks(_static(), TEXT)
    assert all("cache_control" not in b for b in blocks)
    assert "".join(b["text"] for b in blocks) == _static() + _MESSAGE_BLOCK.format(text=TEXT)


def test_every_named_jet_model_is_in_the_prompt():
    """Drift guard between the rules' vocabulary and the prompt. A district the
    LLM recovers brings its whole verdict with it (resolve.py), so a model the
    rules type as jet_drone and the prompt never mentions comes back as
    `missile` — the generic word around it («10 ракет Бандероль») is exactly
    what the model would otherwise go by."""
    from app.parsing.vocab import _JET_MODEL

    prompt = _static().lower()
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

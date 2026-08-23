"""Rule-based parse + optional LLM fallback — the "how did we read this message"
half of the pipeline, kept apart from the tracking handlers.

`should_fallback` is also the exact gate the coverage-gap admin view reuses to
decide "the parser thinks this IS a localizable threat but found no district".
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from ...config import settings
from ...domain.origins import target_not_kyiv
from ...models import RawMessage
from ...parsing import DistrictMatcher, LlmUsage, ParseResult, normalize, parse_message

log = logging.getLogger("ingest")

# How far up a reply chain to look for the promo post that started the thread.
# Real threads nest a couple of levels ("банка на перехоплювачі" -> "закиньте 20
# грн" -> a reply arguing about it); past that the conversation has usually
# drifted somewhere else and the ancestor stops being evidence.
_PROMO_THREAD_DEPTH = 3


def should_fallback(parsed: ParseResult) -> bool:
    """Route to the LLM only when rules couldn't localize a threat-flavored
    message — not for junk/news and not when rules already succeeded."""
    if parsed.aftermath:  # consequence/casualty news — not a live target
        return False
    if parsed.promo:  # donation/ad/channel-boost (link or payment card) — never a target
        return False
    if parsed.siren_only:  # technical "alarm is on here" echo — not a live target
        return False
    if parsed.negated:  # explicit denial ("не йде на...") — not a live target
        return False
    if parsed.civic_notice:  # transport/road city news — not a live target
        return False
    if parsed.eppo_marks:  # dismissed єППО app marks — not a live target
        return False
    if parsed.political_quote:  # official statement repost — not a live target
        return False
    if parsed.chatter:  # buzz-slang reassurance chatter — nothing to localize
        return False
    if parsed.lost_signal:  # "дорозвідка" stand-down — handled directly by ingest, not a live target
        return False
    if parsed.citywide:  # city-level alert with no raion — LLM can't localize it further
        return False
    if parsed.directional:  # rules already raised a directional axis — no district to find
        return False
    if parsed.summary:  # retrospective recap, not a live target — nothing to localize
        return False
    if parsed.target_pulse:  # terse pulse, no place — nothing for the LLM to localize
        return False
    if parsed.notice_kind:  # threat-level bulletin — already surfaced as a feed notice
        return False
    if parsed.districts or parsed.status in ("clear", "destroyed"):
        return False
    # The message names a REGION as the target and no settlement inside it
    # ("Шахед на Чернігівщині", "Ціль на Дніпро") — there is no place in the
    # text for the LLM to recover, watched region or not, so the call would be
    # pure spend. A village we simply don't have yet ("на Пакуль") names no
    # oblast, so it still reaches the LLM, which is the whole point of having a
    # gazetteer enum.
    if target_not_kyiv(normalize(parsed.raw_text)):
        return False
    return parsed.target_type != "unknown" or parsed.status in ("confirmed", "unconfirmed")


async def in_promo_thread(
    session, source_id: int | None, reply_to_message_id: int | None, matcher: DistrictMatcher
) -> bool:
    """Whether this message is a reply inside a donation/ad thread.

    Chatter under a fundraising post argues about the fundraiser, not about
    what's in the sky — but it quotes enough threat vocabulary ("щоб менше
    ворожого лайна літало", "на перехоплення ракет ми не можемо збирати") to
    look like an unlocalized threat to `should_fallback`, and each one costs a
    full LLM call with the whole gazetteer in the prompt (~$0.004). The promo
    post itself is already suppressed; this extends that verdict down its own
    thread. Only walks UP a bounded number of parents, and only over messages
    we stored — an unknown parent ends the walk.
    """
    if source_id is None or reply_to_message_id is None:
        return False
    message_id = reply_to_message_id
    for _ in range(_PROMO_THREAD_DEPTH):
        parent = await session.scalar(
            select(RawMessage).where(
                RawMessage.source_id == source_id, RawMessage.message_id == message_id
            )
        )
        if parent is None:
            return False
        if parse_message(parent.text or "", matcher).promo:
            return True
        if parent.reply_to_message_id is None:
            return False
        message_id = parent.reply_to_message_id
    return False


async def _resolve(
    text: str, matcher: DistrictMatcher, *, allow_llm: bool = True
) -> tuple[ParseResult, str, bool, LlmUsage | None, dict | None]:
    """Rule-based first; LLM fallback only when warranted and configured. The
    3rd return value is whether the LLM was actually CALLED — distinct from
    decision_source=='llm' (which also requires the call to have recovered a
    district); a call that returned nothing still spent the API budget and is
    worth surfacing in /raw_messages. The 4th is its token usage/cost, set
    whenever the call actually completed. The 5th is the LLM's full structured
    response (district_ids + triage category/surface/summary), stored on the
    raw message for /raw audit regardless of whether its districts were used
    (see llm_extract)."""
    parsed = parse_message(text, matcher)
    # `llm_localize_enabled` is off by default: the gazetteer listing this call
    # exists to consult was 81% of the prompt and recovered a district on 6.8% of
    # calls (see parsing/llm.py). With it off, a message that reaches this gate
    # goes to the async triage engine instead — same verdict fields minus the
    # districts, no ingest-lock latency, an eighth of the price.
    if (allow_llm and settings.llm_fallback_enabled and settings.llm_localize_enabled
            and settings.anthropic_api_key and should_fallback(parsed)):
        # Lazy: triage and ingest are mutually recursive (ingest enqueues to
        # triage; triage's rescue calls back into ingest), so this edge stays
        # in-function to avoid an import cycle.
        from ..triage import llm_spend_ok

        # Shared cost guard: when the day/month LLM budget is exhausted, the
        # inline fallback degrades to rules-only too (not just the async engine).
        if not await llm_spend_ok():
            return parsed, "rule", False, None, None
        from ...parsing.llm import llm_extract

        llm, usage, response = await llm_extract(text, matcher)
        # Trust the LLM for LOCALIZATION only — use its result only when it
        # actually recovered a district. Never let it declare an all-clear /
        # destroyed on its own: rules own those via explicit keywords
        # ("відбій"/"збито"), and a keyword-detected stand-down never reaches the
        # LLM anyway (see should_fallback). Letting the LLM infer a clear from a
        # reassuring tone ("масованих пусків немає… відпочивайте") produced false
        # "Відбій" feed entries AND risked closing active tracks via close_all_active.
        # The triage fields (category/surface/summary) are stored via `response`
        # but NOT acted on yet — Stage 1 is collect-only.
        if llm is not None and llm.districts:
            return llm, "llm", True, usage, response
        return parsed, "rule", True, usage, response
    return parsed, "rule", False, None, None

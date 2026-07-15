"""LLM fallback parser (Claude Haiku 4.5) — entity extraction ONLY.

Invoked only when the rule-based parser is low-confidence (see ingest._resolve).
Hard safety rails:
  * The model may pick districts ONLY from a provided enum of known ids — it
    cannot invent a location (structured output enforces the enum).
  * Bearing / ETA / track math stay in deterministic code, never the LLM.
  * A timeout or any error falls back to the rule-based result — the LLM is
    never on the critical path for a safety decision.
"""

from __future__ import annotations

import asyncio
import json
import logging

from anthropic import AsyncAnthropic

from ..config import settings
from .matcher import DistrictHit, DistrictMatcher
from .rules import LlmUsage, ParseResult

log = logging.getLogger("llm")

# Claude Haiku 4.5 pricing (USD per million tokens, as of the model's launch
# pricing) — update alongside settings.llm_model if the model or its price
# changes. Used only to compute the analytics figure on RawMessage; never
# sent to the API.
_INPUT_PRICE_PER_MTOK = 1.00
_OUTPUT_PRICE_PER_MTOK = 5.00

_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


_SYSTEM = (
    "You extract structured aerial-threat data from short Ukrainian Telegram "
    "messages by volunteer spotters watching drones/missiles over Kyiv region. "
    "Return ONLY districts from the provided list, choosing their numeric ids. "
    "If the message names a place not in the list, or is not a sighting/status "
    "report (ads, casualty news, commentary), return an empty district list. "
    "Do not guess coordinates or invent locations. Preserve movement order: "
    "list district ids in the order they appear in the text.\n"
    "CRITICAL — do NOT map other cities/oblasts onto Kyiv districts. A target "
    "'на Дніпро' / 'Дніпропетровщина' is the CITY Dnipro (~300km away), NOT "
    "Kyiv's 'Дніпровський' district — return empty. Likewise Харків, Запоріжжя, "
    "Миколаїв, Чернігів/Чернігівщина, Суми, Полтава and any other city or oblast "
    "are outside Kyiv — return empty. Only localize targets over the Kyiv area "
    "itself; a bare 'на Київ' with no district is also empty."
)

# Triage taxonomy for the operator situational-awareness feed. The model reports
# WHICH of these a district-less message is; the pipeline does NOT route on it
# yet (Stage 1 = collect + audit only) — it's stored on raw_messages.llm_response
# to tune the Stage-3 context layer against real responses.
_CATEGORIES = ("localized", "citywide", "directional", "forecast", "status", "noise")

_PROMPT = (
    "Known districts (id: name):\n{listing}\n\n"
    "Target type: shahed (шахед/мопед/герань/generic БпЛА), jet_drone "
    "(реактивний/швидкісний), ballistic (балістика/іскандер/кинджал/С-400/С-300), "
    "missile (крилата ракета/калібр/Х-101/КАБ/generic ракета), or unknown. Use "
    "ballistic ONLY for an explicit ballistic marker; a bare 'ракета' is missile.\n"
    "Status: confirmed (🔴/підтверджено), unconfirmed (уточнюється/попередньо/"
    "можливо), destroyed (збито/знищено/уражено), clear (відбій), or sighting.\n"
    "is_new_target: true if it marks a new/additional target (новий/ще один/"
    "друга ціль).\n\n"
    "Triage fields (for an operator feed — independent of the district rules "
    "above; picking these NEVER lets you invent or force a district):\n"
    "- category: localized (names a place from the list) | citywide (threat on "
    "Kyiv as a whole, no single raion — 'ціль на місто', 'балістика на Київ') | "
    "directional (only a bearing/axis, no point — 'на правий берег', 'курсом з "
    "півночі') | forecast (a future/expected strike — 'готують масований удар', "
    "'ймовірні пуски') | status (PPO-working / operational status / all-clear "
    "note) | noise (ads, aftermath/casualty news, commentary, other oblasts).\n"
    "- surface: true ONLY if an operator watching Kyiv should SEE this even with "
    "no localized district (a citywide/directional/forecast threat cue); false "
    "for noise and for other oblasts.\n"
    "- summary: when surface is true, a short (<=80 char) Ukrainian operator-"
    "facing line with the actionable gist; empty string otherwise.\n\n"
    "Message:\n{text}"
)


def _schema(id_enum: list[int]) -> dict:
    return {
        "type": "object",
        "properties": {
            "district_ids": {"type": "array", "items": {"type": "integer", "enum": id_enum}},
            "target_type": {"type": "string",
                            "enum": ["shahed", "jet_drone", "missile", "ballistic", "unknown"]},
            "status": {"type": "string",
                       "enum": ["confirmed", "unconfirmed", "destroyed", "clear", "sighting"]},
            "is_new_target": {"type": "boolean"},
            "confidence": {"type": "number"},
            "category": {"type": "string", "enum": list(_CATEGORIES)},
            "surface": {"type": "boolean"},
            "summary": {"type": "string"},
        },
        "required": ["district_ids", "target_type", "status", "is_new_target",
                     "confidence", "category", "surface", "summary"],
        "additionalProperties": False,
    }


def _usage_from(resp) -> LlmUsage:
    input_tokens = resp.usage.input_tokens
    output_tokens = resp.usage.output_tokens
    cost = (input_tokens / 1_000_000) * _INPUT_PRICE_PER_MTOK + (
        output_tokens / 1_000_000
    ) * _OUTPUT_PRICE_PER_MTOK
    return LlmUsage(input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=round(cost, 6))


async def llm_extract(
    text: str, matcher: DistrictMatcher
) -> tuple[ParseResult | None, LlmUsage | None, dict | None]:
    """Returns (result, usage, response). `usage` is set whenever the API
    actually responded — even if the response couldn't be used (no text block,
    bad JSON) — since the call still spent tokens; None only on a call that
    never completed (timeout/network/API error). `response` is the full
    normalized structured JSON the model returned (district_ids + triage:
    category/surface/summary) whenever usable JSON came back — stored verbatim
    on raw_messages for /raw audit and Stage-3 tuning; None otherwise. Nothing
    in the live pipeline routes on the triage fields yet (Stage 1)."""
    index = matcher.districts_index
    name_by_id = dict(index)
    id_enum = [i for i, _ in index]
    listing = "\n".join(f"{i}: {n}" for i, n in index)

    try:
        resp = await asyncio.wait_for(
            _get_client().messages.create(
                model=settings.llm_model,
                max_tokens=400,
                system=_SYSTEM,
                messages=[{"role": "user", "content": _PROMPT.format(listing=listing, text=text)}],
                output_config={"format": {"type": "json_schema", "schema": _schema(id_enum)}},
            ),
            timeout=settings.llm_timeout_s,
        )
    except Exception as ex:  # timeout, network, API error — stay on rule-based
        log.warning("llm fallback skipped: %s", ex)
        return None, None, None

    usage = _usage_from(resp)

    block = next((b for b in resp.content if b.type == "text"), None)
    if block is None:
        return None, usage, None
    try:
        data = json.loads(block.text)
    except (ValueError, TypeError):
        return None, usage, None

    hits = [
        DistrictHit(did, name_by_id[did], i)
        for i, did in enumerate(data.get("district_ids", []))
        if did in name_by_id
    ]
    conf = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
    # Defense-in-depth: validate against the known vocab even though the JSON
    # schema enum should already enforce it — never let a stray value hit the DB.
    target_type = data.get("target_type", "unknown")
    if target_type not in ("shahed", "jet_drone", "missile", "ballistic", "unknown"):
        target_type = "unknown"
    status = data.get("status", "sighting")
    if status not in ("confirmed", "unconfirmed", "destroyed", "clear", "sighting"):
        status = "sighting"
    is_new_target = bool(data.get("is_new_target", False))
    category = data.get("category", "noise")
    if category not in _CATEGORIES:
        category = "noise"
    surface = bool(data.get("surface", False))
    summary = str(data.get("summary", "") or "")
    # The audited response: exactly the structured fields we accepted (enum-
    # validated ids/type/status/category), so /raw shows what the model said,
    # not raw unvalidated JSON. Districts are the model's picks filtered to
    # known ids — identical to the enum-constrained output, just deduped to hits.
    response = {
        "category": category,
        "surface": surface,
        "summary": summary,
        "district_ids": [h.district_id for h in hits],
        "target_type": target_type,
        "status": status,
        "is_new_target": is_new_target,
        "confidence": round(conf, 2),
    }
    matched = bool(hits) or status in ("clear", "destroyed")
    return ParseResult(
        target_type=target_type,
        status=status,
        is_new_target=is_new_target,
        districts=hits,
        confidence=round(conf, 2),
        raw_text=text,
        matched=matched,
    ), usage, response

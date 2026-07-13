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
from .rules import ParseResult

log = logging.getLogger("llm")

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
        },
        "required": ["district_ids", "target_type", "status", "is_new_target", "confidence"],
        "additionalProperties": False,
    }


async def llm_extract(text: str, matcher: DistrictMatcher) -> ParseResult | None:
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
        return None

    block = next((b for b in resp.content if b.type == "text"), None)
    if block is None:
        return None
    try:
        data = json.loads(block.text)
    except (ValueError, TypeError):
        return None

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
    matched = bool(hits) or status in ("clear", "destroyed")
    return ParseResult(
        target_type=target_type,
        status=status,
        is_new_target=bool(data.get("is_new_target", False)),
        districts=hits,
        confidence=round(conf, 2),
        raw_text=text,
        matched=matched,
    )

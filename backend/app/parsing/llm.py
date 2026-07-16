"""LLM parser (Claude Haiku 4.5) — two consumers over ONE prompt/schema.

1. `llm_extract` — the INLINE, synchronous localization fallback (unchanged
   behavior/contract): called from ingest._resolve while the ingest lock is held
   when rules couldn't localize a threat-flavored message. Its result is used
   for DISTRICTS only.
2. `llm_triage` — the ASYNC second-pass triage (app/pipeline/triage.py): returns
   the full structured verdict (category/surface/summary/origin/…) so the
   context layer can route directional/forecast/status notices, feed the axis
   layer, and (behind a flag) rescue a wrongly-suppressed live threat.

Hard safety rails (both paths):
  * Districts ONLY from the provided enum of known ids — the model cannot invent
    a location (structured output enforces the enum).
  * Origins ONLY from the curated origin enum (origins.ORIGIN_KEYS) — same idea.
  * Bearing / ETA / sector geometry stay in deterministic code, never the LLM.
  * A timeout or any error falls back to the rule-based result — the LLM is
    never on the critical path for a safety decision.
"""

from __future__ import annotations

import asyncio
import json
import logging

from anthropic import AsyncAnthropic

from ..config import settings
from ..domain.origins import ORIGIN_KEYS
from ..domain.origins import SECTORS as _SECTORS
from .matcher import DistrictHit, DistrictMatcher
from .rules import LlmUsage, ParseResult

log = logging.getLogger("llm")

# Claude Haiku 4.5 pricing (USD per million tokens, as of the model's launch
# pricing) — update alongside settings.llm_model if the model or its price
# changes. Used only to compute the analytics figure on RawMessage; never
# sent to the API.
_INPUT_PRICE_PER_MTOK = 1.00
_OUTPUT_PRICE_PER_MTOK = 5.00

_SCHEMA_VERSION = 2

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
    "itself; a bare 'на Київ' with no district is also empty.\n"
    "ORIGIN is different from a target location: an INBOUND threat's launch/"
    "approach zone ('з Брянщини', 'з боку Чорного моря', 'курсом з півночі') is "
    "reported via origin_place / origin_sector, NEVER as a Kyiv district. Pick "
    "origin_place ONLY from the provided origin list, and ONLY when the text "
    "names it as where the threat is coming FROM; otherwise 'none'."
)

# Triage taxonomy for the operator situational-awareness feed.
_CATEGORIES = ("localized", "citywide", "directional", "forecast", "status", "noise")

_PROMPT = (
    "Known districts (id: name):\n{listing}\n\n"
    "Known origins (key): {origins}. Use an origin key ONLY for an inbound "
    "threat's launch/approach zone named with 'з/від/з боку/з напрямку'; else "
    "'none'.\n\n"
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
    "directional (an inbound axis/origin, no Kyiv point — 'балістика з Брянська', "
    "'на правий берег', 'курсом з півночі') | forecast (a future/expected strike "
    "— 'готують масований удар', 'ймовірні пуски', 'червоний рівень по балістиці') "
    "| status (PPO-working / operational-status / calm note — 'спокійно по "
    "балістиці', 'сили ППО працюють') | noise (ads, aftermath/casualty news, "
    "commentary, other oblasts as the TARGET).\n"
    "- origin_place: an origin key from the list when category is directional and "
    "a listed origin is named as the source; else 'none'.\n"
    "- origin_sector: N|NE|E|SE|S|SW|W|NW when the text states a compass bearing "
    "the threat comes from ('з півночі'->N, 'зі сходу'->E); else 'none'. Report "
    "only what the text says — never infer a sector from a place name.\n"
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
            "origin_place": {"type": "string", "enum": [*ORIGIN_KEYS, "none"]},
            "origin_sector": {"type": "string", "enum": [*_SECTORS, "none"]},
            "surface": {"type": "boolean"},
            "summary": {"type": "string"},
        },
        "required": ["district_ids", "target_type", "status", "is_new_target",
                     "confidence", "category", "origin_place", "origin_sector",
                     "surface", "summary"],
        "additionalProperties": False,
    }


def _usage_from(resp) -> LlmUsage:
    input_tokens = resp.usage.input_tokens
    output_tokens = resp.usage.output_tokens
    cost = (input_tokens / 1_000_000) * _INPUT_PRICE_PER_MTOK + (
        output_tokens / 1_000_000
    ) * _OUTPUT_PRICE_PER_MTOK
    return LlmUsage(input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=round(cost, 6))


async def _call(text: str, matcher: DistrictMatcher) -> tuple[dict | None, LlmUsage | None]:
    """Shared transport for both entry points: one API call (with a single
    immediate retry on a transient error), returning (parsed_json, usage).

    `usage` is set whenever the API actually responded — even if the response
    body couldn't be used — since the call still spent tokens; None only on a
    call that never completed (timeout/network/API error). `parsed_json` is the
    raw structured JSON (enum-constrained by the schema) or None when nothing
    usable came back."""
    index = matcher.districts_index
    listing = "\n".join(f"{i}: {n}" for i, n in index)
    id_enum = [i for i, _ in index]
    content = _PROMPT.format(listing=listing, origins=", ".join(ORIGIN_KEYS), text=text)
    schema = _schema(id_enum)
    # One immediate retry: a transient timeout/5xx during a mass attack (many
    # concurrent inbound callouts) dropped GENUINE threats — a real inbound "3
    # реактивних з Чернігівщини" is worth a second attempt. No backoff: the
    # inline path holds the ingest lock, so a sleep would stall the pipeline.
    resp = None
    for attempt in range(2):
        try:
            resp = await asyncio.wait_for(
                _get_client().messages.create(
                    model=settings.llm_model,
                    max_tokens=400,
                    system=_SYSTEM,
                    messages=[{"role": "user", "content": content}],
                    output_config={"format": {"type": "json_schema", "schema": schema}},
                ),
                timeout=settings.llm_timeout_s,
            )
            break
        except Exception as ex:  # timeout, network, API error
            if attempt == 1:
                log.warning("llm call skipped after 2 attempts: %s", ex)
                return None, None
            log.info("llm call retrying after: %s", ex)

    usage = _usage_from(resp)
    block = next((b for b in resp.content if b.type == "text"), None)
    if block is None:
        return None, usage
    try:
        return json.loads(block.text), usage
    except (ValueError, TypeError):
        return None, usage


def _normalize(data: dict, matcher: DistrictMatcher) -> tuple[list[DistrictHit], dict]:
    """Enum-validate the raw JSON (defense-in-depth beyond the schema) and build
    (district hits, stored verdict dict). The verdict is exactly the fields we
    accepted, so /raw shows what the model said — not raw unvalidated JSON."""
    name_by_id = dict(matcher.districts_index)
    hits = [
        DistrictHit(did, name_by_id[did], i)
        for i, did in enumerate(data.get("district_ids", []))
        if did in name_by_id
    ]
    conf = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
    target_type = data.get("target_type", "unknown")
    if target_type not in ("shahed", "jet_drone", "missile", "ballistic", "unknown"):
        target_type = "unknown"
    status = data.get("status", "sighting")
    if status not in ("confirmed", "unconfirmed", "destroyed", "clear", "sighting"):
        status = "sighting"
    category = data.get("category", "noise")
    if category not in _CATEGORIES:
        category = "noise"
    origin_place = data.get("origin_place", "none")
    if origin_place not in ORIGIN_KEYS:
        origin_place = "none"
    origin_sector = data.get("origin_sector", "none")
    if origin_sector not in _SECTORS:
        origin_sector = "none"
    verdict = {
        "schema_version": _SCHEMA_VERSION,
        "category": category,
        "origin_place": origin_place,
        "origin_sector": origin_sector,
        "surface": bool(data.get("surface", False)),
        "summary": str(data.get("summary", "") or ""),
        "district_ids": [h.district_id for h in hits],
        "target_type": target_type,
        "status": status,
        "is_new_target": bool(data.get("is_new_target", False)),
        "confidence": round(conf, 2),
    }
    return hits, verdict


async def llm_extract(
    text: str, matcher: DistrictMatcher
) -> tuple[ParseResult | None, LlmUsage | None, dict | None]:
    """INLINE localization fallback. Returns (result, usage, response). `result`
    carries only the LOCALIZATION fields (districts/type/status) — ingest uses
    its districts only. `response` is the full verdict (triage + origin) stored
    verbatim on raw_messages for /raw audit and for the async triage engine to
    reuse without a second API call."""
    data, usage = await _call(text, matcher)
    if data is None:
        return None, usage, None
    hits, verdict = _normalize(data, matcher)
    matched = bool(hits) or verdict["status"] in ("clear", "destroyed")
    return ParseResult(
        target_type=verdict["target_type"],
        status=verdict["status"],
        is_new_target=verdict["is_new_target"],
        districts=hits,
        confidence=verdict["confidence"],
        raw_text=text,
        matched=matched,
    ), usage, verdict


async def llm_triage(
    text: str, matcher: DistrictMatcher
) -> tuple[dict | None, LlmUsage | None]:
    """ASYNC second-pass triage. Returns (verdict, usage) — the full structured
    verdict the routing table in app/pipeline/triage.py consumes, or (None, usage)
    when no usable JSON came back."""
    data, usage = await _call(text, matcher)
    if data is None:
        return None, usage
    _, verdict = _normalize(data, matcher)
    return verdict, usage

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
# Prompt-caching multipliers on the INPUT price: writing the cache costs more
# than a plain call, reading it costs a tenth. See settings.llm_cache_ttl.
_CACHE_WRITE_MULT = {"5m": 1.25, "1h": 2.00}
_CACHE_READ_MULT = 0.10

_SCHEMA_VERSION = 2

_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


# How each watched region is named to the model — Ukrainian, because every
# other word in the prompt's examples is.
_REGION_LABEL = {"kyiv": "Київщина", "chernihiv": "Чернігівщина"}

_SYSTEM = (
    "You extract structured aerial-threat data from short Ukrainian Telegram "
    "messages by volunteer spotters watching drones/missiles over the Kyiv "
    "region AND over Чернігівщина, the northern approach corridor toward it. "
    "Return ONLY districts from the provided list, choosing their numeric ids. "
    "If the message names a place not in the list, or is not a sighting/status "
    "report (ads, casualty news, commentary), return an empty district list. "
    "Do not guess coordinates or invent locations. Preserve movement order: "
    "list district ids in the order they appear in the text.\n"
    "CRITICAL — do NOT map an out-of-scope city/oblast onto a same-sounding "
    "district. A target 'на Дніпро' / 'Дніпропетровщина' is the CITY Dnipro "
    "(~300km away), NOT 'Дніпровський' district — return empty. Likewise "
    "Харків, Запоріжжя, Миколаїв, Суми, Полтава and any oblast other than the "
    "two watched ones are out of scope — return empty. Each place in the list "
    "is tagged with its region; when a name exists on both sides of the border "
    "(Лебедівка, Рокитне, Дніпровське) pick the region of the places named "
    "around it. A bare 'на Київ' with no district is empty, and so is a bare "
    "'на Чернігівщину' with no settlement named.\n"
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
    # The type list has to mirror rules._target_type, including the named jet
    # models: when this call recovers a district, ingest takes its WHOLE verdict
    # (resolve.py) — type included — so anything the rules know and the prompt
    # doesn't is silently downgraded on exactly the messages the rules could not
    # localize. «Бандероль» is the live case: the same night calls it a «ракета»
    # and a «баражуючий боєприпас», both of which point this model elsewhere.
    "Target type: shahed (шахед/мопед/герань/generic БпЛА), jet_drone "
    "(реактивний/швидкісний/Бандероль), ballistic (балістика/іскандер/кинджал/"
    "С-400/С-300), missile (крилата ракета/калібр/Х-101/КАБ/generic ракета), or "
    "unknown. Use ballistic ONLY for an explicit ballistic marker; a bare "
    "'ракета' is missile. A named model wins over the word around it: "
    "«Бандероль» is jet_drone however the message words it ('10 ракет "
    "Бандероль', 'баражуючий боєприпас типу Бандероль').\n"
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
    "— 'готують масований удар', 'ймовірні пуски', 'червоний рівень по балістиці'; "
    "ONLY about the future, stated by the text itself — a tally of strikes that "
    "ALREADY happened is status, and a bare count with no verb ('21 ракета + 8 "
    "Цирконів') is status too, never forecast; a description of the STANDING "
    "background risk rather than a new development is noise, not forecast — "
    "'загроза балістики вже півтора місяці на постійній основі, про це не треба "
    "писати щовечора' announces nothing and must not become a threat card) "
    "| status (PPO-working / operational-status / calm note / a recap or count of "
    "what already hit — 'спокійно по балістиці', 'сили ППО працюють', 'це вже "
    "десь під 40 ракет', 'загалом було до 35 ракет') | noise (ads, "
    "aftermath/casualty news, commentary, an UNWATCHED oblast as the TARGET — "
    "Чернігівщина is watched, so a target there is a sighting, not noise).\n"
    "- origin_place: an origin key from the list when category is directional and "
    "a listed origin is named as the source; else 'none'.\n"
    "- origin_sector: N|NE|E|SE|S|SW|W|NW when the text states a compass bearing "
    "the threat comes from ('з півночі'->N, 'зі сходу'->E); else 'none'. Report "
    "only what the text says — never infer a sector from a place name.\n"
    "- surface: true ONLY if an operator watching Kyiv should SEE this even with "
    "no localized district (a citywide/directional/forecast threat cue); false "
    "for noise and for other oblasts.\n"
    "- summary: when surface is true, a short (<=80 char) operator-facing line "
    "with the actionable gist, in natural Ukrainian ONLY (no English or "
    "transliterated words); state facts as reported — a recap stays past-tense "
    "('було ~40 ракет'), never rephrased as expected ('очікуються'); empty "
    "string otherwise.\n\n"   # the blank line that used to precede "Message:"
)
# The message is its OWN content block, and everything above is the cacheable
# prefix — see _content_blocks. Nothing but this line may follow the district
# listing and the instructions, or the prefix stops being a prefix.
_MESSAGE_BLOCK = "Message:\n{text}"


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


def _content_blocks(static: str, text: str) -> list[dict]:
    """The user turn as two blocks: the static prefix (district listing +
    instructions), then the message. The cache breakpoint goes at the end of the
    first one, so everything before it — system prompt included — is what gets
    cached and re-read at a tenth of the price. With caching off it is still two
    blocks, which the API concatenates exactly as the single string used to be."""
    blocks: list[dict] = [
        {"type": "text", "text": static},
        {"type": "text", "text": _MESSAGE_BLOCK.format(text=text)},
    ]
    if settings.llm_cache_ttl:
        blocks[0]["cache_control"] = {"type": "ephemeral", "ttl": settings.llm_cache_ttl}
    return blocks


def _usage_from(resp) -> LlmUsage:
    """Token usage + REAL cost, which caching splits three ways: fresh input at
    full price, a cache write at 1.25x (5m) / 2x (1h), and a cache read at 0.1x.

    `input_tokens` is reported as the whole prompt (fresh + cached) so the
    number stays comparable with the pre-caching rows in /raw and the analytics;
    only the cost differs. Getting this wrong would also mis-drive the daily/
    monthly budget guard, which sums exactly this column."""
    usage = resp.usage
    fresh = usage.input_tokens
    written = getattr(usage, "cache_creation_input_tokens", None) or 0
    read = getattr(usage, "cache_read_input_tokens", None) or 0
    output_tokens = usage.output_tokens
    write_mult = _CACHE_WRITE_MULT.get(settings.llm_cache_ttl, 1.25)
    cost = (
        (fresh + written * write_mult + read * _CACHE_READ_MULT) / 1_000_000
    ) * _INPUT_PRICE_PER_MTOK + (output_tokens / 1_000_000) * _OUTPUT_PRICE_PER_MTOK
    return LlmUsage(
        input_tokens=fresh + written + read,
        output_tokens=output_tokens,
        cost_usd=round(cost, 6),
    )


async def _call(text: str, matcher: DistrictMatcher) -> tuple[dict | None, LlmUsage | None]:
    """Shared transport for both entry points: one API call (with a single
    immediate retry on a transient error), returning (parsed_json, usage).

    `usage` is set whenever the API actually responded — even if the response
    body couldn't be used — since the call still spent tokens; None only on a
    call that never completed (timeout/network/API error). `parsed_json` is the
    raw structured JSON (enum-constrained by the schema) or None when nothing
    usable came back."""
    index = matcher.districts_index
    # Each line carries its region: two watched regions share the enum, and
    # several names exist in both, so the id alone is ambiguous to the model.
    listing = "\n".join(
        f"{i}: {n} [{_REGION_LABEL.get(matcher.region_by_id.get(i, ''), 'Київщина')}]"
        for i, n in index
    )
    id_enum = [i for i, _ in index]
    static = _PROMPT.format(listing=listing, origins=", ".join(ORIGIN_KEYS))
    schema = _schema(id_enum)
    # One immediate retry: a transient timeout/5xx during a mass attack (many
    # concurrent inbound callouts) dropped GENUINE threats — a real inbound "3
    # реактивних з Чернігівщини" is worth a second attempt. No backoff: the
    # inline path holds the ingest lock, so a sleep would stall the pipeline.
    #
    # The LAST attempt drops the cache breakpoint. If an account or model ever
    # refuses the cache_control block (or the '1h' TTL), the failure would
    # otherwise be systematic and silent — every call dying twice and the
    # pipeline quietly degrading to rules-only for as long as nobody looks at
    # the logs. Paying full price beats going blind.
    resp = None
    blocks = _content_blocks(static, text)
    for attempt in range(2):
        try:
            resp = await asyncio.wait_for(
                _get_client().messages.create(
                    model=settings.llm_model,
                    max_tokens=400,
                    system=_SYSTEM,
                    messages=[{"role": "user", "content": blocks}],
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
            blocks = [{k: v for k, v in b.items() if k != "cache_control"} for b in blocks]

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

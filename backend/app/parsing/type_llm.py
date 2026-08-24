"""LLM target-type classifier (Claude Haiku 4.5) — the third consumer of the
LLM, and the one the gazetteer's prompt budget moved to.

Why this exists. 79% of localizable sightings never name a target type: the
northern spotters shout bare toponyms («На хоробичі», «Троя/Воскресенка 3х 🔴»)
because the wave was announced once, half an hour earlier, possibly in another
channel. Rules can't recover what the sentence doesn't contain, so the pipeline
already has two context tiers — the per-channel `_note_and_inherit_type` window
and the incident-level prior — and they still leave ~46% of sightings untyped,
i.e. a generic dot on the map with the wrong stale window.

Why the context is WIDE. Measured on 25 real untyped sightings from the corpus:
the same classifier given 6 messages of the sighting's OWN channel over 30
minutes typed 3 of 25; given 25 messages of ALL channels over 2 hours it typed
22 of 25 (1 352 prompt tokens, $0.0015, p90 1.5s). The narrow window isn't a
cheaper version of this feature — it's a version that doesn't work.

Safety rails:
  * Output is enum-railed by structured output: five known types, nothing else.
  * It is a FOURTH tier — it only ever runs when the text, the channel context
    and the incident prior all said `unknown`, so it can never overrule a type
    the rules read out of the message.
  * `evidence` says where the answer came from, so `context` guesses can be
    audited (and filtered) separately from a type actually written in the text.
  * No retry: unlike localization, a missed call costs nothing but an untyped
    marker, and this one runs while ingest holds the lock.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

from ..config import settings
from .llm import _get_client, _usage_from
from .rules import LlmUsage

log = logging.getLogger("llm")

TYPES = ("shahed", "jet_drone", "missile", "ballistic", "unknown")
EVIDENCE = ("text", "context", "none")

_SYSTEM = (
    "Ти — аналітик ППО-фіду. Визначаєш ТИП повітряної цілі, про яку йдеться в "
    "цільовому повідомленні українського спостерігача (Київщина/Чернігівщина). "
    "Дається стрічка попередніх повідомлень усіх каналів за останні дві години "
    "(з мітками каналу та часу) — це поточна картина в небі.\n"
    "Типи: shahed (шахед/мопед/герань/БпЛА), jet_drone (реактивний/швидкісний/"
    "Бандероль), ballistic (балістика/іскандер-М/кинджал/С-300/С-400), missile "
    "(крилата ракета/калібр/Х-101/КАБ/іскандер-К), unknown.\n"
    "Більшість цільових повідомлень — це голі топоніми («На сосницю», «Троя 🔴»), "
    "тип у них не названо. Це НОРМА: визнач тип із стрічки — якщо в цей момент у "
    "небі йде хвиля одного типу (її оголосили раніше або вона видно з сусідніх "
    "викликів), ця ціль майже напевно того ж типу. Тримай ланцюжок: послідовні "
    "топоніми одного каналу — це зазвичай та сама ціль, що рухається.\n"
    "Назва моделі важливіша за родове слово («Бандероль» = jet_drone, навіть "
    "якщо названа ракетою). Гола «ракета» без ознак балістики = missile.\n"
    "НЕ бери тип із: повідомлень про носіїв («злетіли тушки», «з оленя»), "
    "прогнозів («можлива хвиля балістики», «готують удар»), підсумків ночі, "
    "заперечень, реклами/зборів — вони не про те, що зараз у небі. Якщо у "
    "стрічці одночасно дві різні хвилі і незрозуміло, до якої належить ціль — "
    "unknown.\n"
    "evidence: text (тип названо у самому цільовому повідомленні), context "
    "(взято зі стрічки), none (визначити неможливо). confidence: 0..1."
)

_PROMPT = (
    "Стрічка (найстаріше зверху):\n{context}\n\n"
    "Цільове повідомлення ({source}):\n{text}"
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "target_type": {"type": "string", "enum": list(TYPES)},
        "evidence": {"type": "string", "enum": list(EVIDENCE)},
        "confidence": {"type": "number"},
    },
    "required": ["target_type", "evidence", "confidence"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class TypeVerdict:
    """What the classifier said. Stored on the raw message verbatim so a
    reprocess replays it instead of paying for it again, and so shadow mode can
    be reviewed against what the rules decided."""

    target_type: str
    evidence: str
    confidence: float

    @property
    def usable(self) -> bool:
        """Whether this may be applied to a live message. A type with no
        evidence is the model declining, not a low-confidence guess."""
        return (
            self.target_type != "unknown"
            and self.evidence != "none"
            and self.confidence >= settings.llm_type_min_confidence
        )

    @property
    def declined(self) -> bool:
        """Whether the model said it CANNOT tell, as opposed to answering
        weakly. The other half of the distinction `usable` draws, and the one
        that decides whether re-asking is worth anything: a decline will repeat
        until the feed gains a stated type, while a 0.65 answer genuinely
        firmed up to 0.75 thirty-seven seconds later on 2026-08-23. See
        ingest/context.type_context_declined."""
        return self.target_type == "unknown" or self.evidence == "none"


async def llm_target_type(
    text: str, context: str, source_label: str
) -> tuple[TypeVerdict | None, LlmUsage | None]:
    """Classify one message against the recent feed. Returns (verdict, usage);
    verdict is None when the call never completed or returned nothing usable —
    the caller then simply stays `unknown`.

    `usage` is set whenever the API responded (tokens were spent even if the
    body was unusable), so the daily/monthly budget guard sees every call."""
    prompt = _PROMPT.format(context=context or "(порожньо)", source=source_label, text=text)
    try:
        resp = await asyncio.wait_for(
            _get_client().messages.create(
                model=settings.llm_model,
                max_tokens=100,
                system=_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
            ),
            timeout=settings.llm_type_timeout_s,
        )
    except Exception as ex:  # timeout, network, API error
        log.info("llm type call skipped: %s", ex)
        return None, None

    usage = _usage_from(resp)
    block = next((b for b in resp.content if b.type == "text"), None)
    if block is None:
        return None, usage
    try:
        data = json.loads(block.text)
    except (ValueError, TypeError):
        return None, usage
    return normalize_type_verdict(data), usage


def normalize_type_verdict(data: dict) -> TypeVerdict:
    """Enum-validate the raw JSON — defense in depth behind the schema, and the
    single place a STORED verdict is re-read from on reprocess."""
    target_type = data.get("target_type", "unknown")
    if target_type not in TYPES:
        target_type = "unknown"
    evidence = data.get("evidence", "none")
    if evidence not in EVIDENCE:
        evidence = "none"
    try:
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0
    return TypeVerdict(target_type=target_type, evidence=evidence,
                       confidence=round(confidence, 2))

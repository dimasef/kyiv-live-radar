"""Best-effort explanation of what the pipeline decided about a raw message —
used by the /raw debug view (see api/public/raw.py).

Re-runs the pure rule parser read-only: no LLM call, no DB writes, so this never
touches the live pipeline. That also means it reflects TODAY's rules, not
whatever ran when the message was ingested — after a parser change an old row's
diagnosis can legitimately disagree with the events it actually produced. Both
`RawMessageOut.suppressed_by` and `.parsed` carry that caveat.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..parsing import DistrictMatcher, ParseResult, parse_message

# Checked in order — the first flag that's set wins. `flag` is the machine name
# (stable, for filtering/aggregating an export); `label` is what /raw shows.
# Ordering matters: the earlier entries genuinely suppress, the later ones are
# routing decisions (the message WAS acted on, just not as a new sighting card).
_SUPPRESSION_LABELS: list[tuple[str, str]] = [
    ("aftermath", "хроніка наслідків"),
    ("promo", "реклама/донат"),
    ("civic_notice", "міська новина"),
    ("eppo_marks", "марки єППО"),
    ("ground_war", "новина з фронту"),
    ("personal_post", "особистий пост"),
    ("negated", "заперечення"),
    ("siren_only", "лише сирена"),
    ("political_quote", "цитата/політика"),
    ("reportage", "переказ новини"),
    ("day_recap", "денний підсумок"),
    ("lost_signal", "втрата сигналу"),
    ("summary", "підсумок атаки"),
    # Below this line: not suppressors. Without them these rows all collapsed
    # into the "не про загрозу" catch-all, which was ~a quarter of the feed and
    # explained nothing (2026-08-02 export review).
    ("ad_action", "робота ППО"),
    ("citywide", "загроза на місто"),
    ("directional", "напрямок загрози"),
    ("target_pulse", "короткий пульс"),
    ("chatter", "балачка"),
]


@dataclass
class Diagnosis:
    label: str  # human-readable outcome shown in /raw
    flag: str | None  # machine name of the deciding rule, None if none fired
    parsed: ParseResult  # the full read-only re-parse, for the export snapshot


def diagnose(text: str, matcher: DistrictMatcher) -> Diagnosis:
    parsed = parse_message(text, matcher)
    for attr, label in _SUPPRESSION_LABELS:
        if getattr(parsed, attr):
            return Diagnosis(label=label, flag=attr, parsed=parsed)
    if not parsed.matched:
        if parsed.target_type != "unknown":
            return Diagnosis("без району", "no_district", parsed)
        return Diagnosis("не про загрозу", "not_threat", parsed)
    # matched=True but no recorded ThreatEvent — a clear/destroyed/citywide
    # update to an existing track rather than a new sighting card, or an
    # LLM-only fallback (rules alone wouldn't have found the district this
    # read-only re-run just used).
    return Diagnosis("оброблено, без нової картки", None, parsed)

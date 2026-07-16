"""Best-effort explanation of why a raw message did NOT surface as a live
sighting card — used only when no ThreatEvent matches it (see
routes.py's /raw_messages). Re-runs the pure rule parser read-only: no LLM
call, no DB writes, so this never touches the live pipeline."""

from __future__ import annotations

from ..parsing import DistrictMatcher, parse_message

# Checked in order — the first suppression flag that's set wins the label.
_SUPPRESSION_LABELS: list[tuple[str, str]] = [
    ("aftermath", "хроніка наслідків"),
    ("promo", "реклама/донат"),
    ("civic_notice", "міська новина"),
    ("eppo_marks", "марки єППО"),
    ("negated", "заперечення"),
    ("siren_only", "лише сирена"),
    ("political_quote", "цитата/політика"),
    ("day_recap", "денний підсумок"),
    ("lost_signal", "втрата сигналу"),
    ("summary", "підсумок атаки"),
]


def diagnose(text: str, matcher: DistrictMatcher) -> str:
    parsed = parse_message(text, matcher)
    for attr, label in _SUPPRESSION_LABELS:
        if getattr(parsed, attr):
            return label
    if not parsed.matched:
        return "без району" if parsed.target_type != "unknown" else "не про загрозу"
    # matched=True but no recorded ThreatEvent — a clear/destroyed/citywide
    # update to an existing track rather than a new sighting card, or an
    # LLM-only fallback (rules alone wouldn't have found the district this
    # read-only re-run just used).
    return "оброблено, без нової картки"

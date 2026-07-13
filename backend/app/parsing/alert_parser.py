"""Parser for the official alert channel (@KyivCityOfficial) — separate from
the spotter parser (parser.py) since the two vocabularies don't mix: this
channel posts real тривога/відбій announcements interleaved with ordinary
city news (infrastructure updates, aftermath reports, weekly recaps), so
routing it through the spotter parser would let its own "Відбій…" trip the
spotter's all-clear keyword and close active tracks prematurely — a decision
deferred to Phase 3, not a bug here (see telegram_listener.py routing).

Rules below are built from a real backfill of the channel — see
tests/data/alert_channel_sample.jsonl (27 messages, 2026-07-10..12) and
test_alert_parser.py, which runs every rule against that fixture. Only one
start/end cycle has been observed live so far (the 2026-07-11 ballistic
night) — extend the fixture and these patterns together as more real
formulations show up, per the project's "sweep the real corpus before
committing a heuristic" discipline (see gazetteer.py's stem-collision notes).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ParsedAlert:
    scope: str  # 'city' | 'oblast'
    action: str  # 'start' | 'end'


# Matches the real observed phrasing "оголошена повітряна тривога" /
# "оголошено повітряну тривогу" — deliberately the full three-word phrase,
# not just "оголош.*тривог", because the real відбій message ALSO contains
# "оголошення тривоги" in a conditional clause ("...у разі оголошення
# тривоги, повернутися до укриття") with no "повітрян*" nearby. Requiring all
# three stems in sequence keeps that clause from being misread as a new start.
_START_RE = re.compile(r"оголошен\w*\s+повітрян\w*\s+тривог\w*", re.IGNORECASE)

# The channel also duplicates every alert as a fixed-template English post
# (observed verbatim, no variation so far): "ATTENTION! Air raid sirens in
# Kyiv" / "Air siren all clear". Requires "in kyiv" right after "air raid
# siren(s)", not just the bare phrase — the bilingual weekly recap says
# "the capital had 13 air raid sirens" as a stat (English mirror of the
# same "13 повітряних тривог" false positive _START_RE avoids), with no
# "in kyiv" nearby.
_START_EN_RE = re.compile(r"air raid sirens?\s+in\s+kyiv", re.IGNORECASE)

# "област*" (stem covers область/області/областю/...) or "обл." anywhere in
# the message -> oblast-scoped; the real city alert never names a scope at
# all ("У Києві оголошена..."), so city is the default rather than requiring
# an explicit "Київ"/"столиц" mention.
_OBLAST_MARKERS = ("област", "обл.")


def parse_alert_message(text: str) -> ParsedAlert | None:
    """Real тривога/відбій announcement -> a scope+action pair, else None
    (city news, weekly recaps, aftermath reports — the majority of this
    channel's traffic). відбій/all-clear is checked BEFORE start in each
    language — see _START_RE.
    """
    low = text.lower()

    if "відбій" in low and "тривог" in low:
        return ParsedAlert(scope=_scope(low), action="end")
    if "siren" in low and "all clear" in low:
        return ParsedAlert(scope=_scope(low), action="end")

    if _START_RE.search(low):
        return ParsedAlert(scope=_scope(low), action="start")
    if _START_EN_RE.search(low):
        return ParsedAlert(scope=_scope(low), action="start")

    return None


def _scope(low: str) -> str:
    return "oblast" if any(m in low for m in _OBLAST_MARKERS) else "city"

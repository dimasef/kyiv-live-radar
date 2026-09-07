"""Parser for the official alert channel (@KyivCityOfficial) — separate from
the spotter parser (parser.py) since the two vocabularies don't mix: this
channel posts real тривога/відбій announcements interleaved with ordinary
city news (infrastructure updates, aftermath reports, weekly recaps), so
routing it through the spotter parser would let its own "Відбій…" trip the
spotter's all-clear keyword and close active tracks prematurely — a decision
deferred to Phase 3, not a bug here (see telegram_listener.py routing).

Since 06:00 on 2026-09-06 the channel announces a DIFFERENTIATED alert, and
the government's taxonomy is published verbatim in the channel's own post
20351:

    🟡 Жовтий рівень:  "Дронова небезпека".
    🔴 Червоний рівень: "Масована дронова загроза"; "Ракетна загроза";
       "Ракетно-дронова загроза".
    🟢 "Відбій" – загрози та небезпеки відсутні.

Note the wording split the levels themselves follow: the yellow level is the
only one called «небезпека», every red one is a «загроза». That is the rule
encoded below, so a fifth phrasing lands on the right level by default.

Rules are built from a real backfill of the channel — see
tests/data/alert_channel_sample.jsonl and test_alert_parser.py, which runs
every rule against that fixture.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import AlertLevel, AlertThreat


@dataclass
class ParsedAlert:
    scope: str  # 'city' | 'oblast'
    action: str  # 'start' | 'end'
    # 'unknown' for the pre-differentiation announcement, which named no level
    # — and still arrives from channels outside Kyiv.
    level: AlertLevel = "unknown"
    threat: AlertThreat = "unspecified"


# Every announcement is a one-line headline with the body below it, and both
# rules below read THAT LINE ONLY. This is not tidiness — it is the guard that
# keeps the channel's own explainer posts out. Post 20351 spells the whole new
# taxonomy out in its body ("Дронова небезпека", "Ракетна загроза", and
# «Повідомлення "Відбій" означає…») and a whole-text match reads it as three
# contradictory signals at once. Widening this window past the first line
# re-admits it.
_THREATS: tuple[tuple[re.Pattern[str], AlertLevel, AlertThreat], ...] = (
    # Before the bare ракетн* rule: "ракетно-дронова" is a different threat and
    # would otherwise be read as a plain missile one.
    (re.compile(r"ракетно-дронов\w*\s+(?:загроз|небезпек)"), "red", "missile_drone"),
    (re.compile(r"масован\w*\s+дронов\w*\s+(?:загроз|небезпек)"), "red", "massed_drone"),
    (re.compile(r"ракетн\w*\s+(?:загроз|небезпек)"), "red", "missile"),
    (re.compile(r"дронов\w*\s+небезпек"), "yellow", "drone"),
    # Not in the published taxonomy, but «загроза» is the red half of its own
    # naming rule — an unqualified drone THREAT is read as the massed one
    # rather than quietly downgraded to yellow.
    (re.compile(r"дронов\w*\s+загроз"), "red", "massed_drone"),
    # The pre-06.09 announcement, still the wording every non-Kyiv alert
    # channel uses. Deliberately the full three-word phrase, not just
    # "оголош.*тривог", because the real відбій message ALSO contains
    # "оголошення тривоги" in a conditional clause ("...у разі оголошення
    # тривоги, повернутися до укриття").
    (re.compile(r"повітрян\w*\s+тривог"), "unknown", "unspecified"),
)

# The headline of a start announcement always declares one ("У Києві ОГОЛОШЕНА
# дронова небезпека"). Requiring it is what keeps a headline that merely names
# a threat — «Про перевезення пасажирів … під час жовтого та червоного рівня
# загрози» (20356) — from opening an alert.
_DECLARED_RE = re.compile(r"оголошен")

# The channel also duplicates the LEGACY alert as a fixed-template English post
# ("ATTENTION! Air raid sirens in Kyiv"). Requires "in kyiv" right after "air
# raid siren(s)", not just the bare phrase — the bilingual weekly recap says
# "the capital had 13 air raid sirens" as a stat. The new differentiated
# announcements carry no English mirror at all.
_START_EN_RE = re.compile(r"air raid sirens?\s+in\s+kyiv")

# Anchored to the very start of the headline, so «Повідомлення "Відбій"
# означає…» inside an explainer can never end a running alert.
_END_RE = re.compile(r"^\W*відбій")
_END_EN_RE = re.compile(r"all clear")

# "област*" (stem covers область/області/областю/...) or "обл." anywhere in
# the message -> oblast-scoped; the real city alert never names a scope at
# all ("У Києві оголошена..."), so city is the default rather than requiring
# an explicit "Київ"/"столиц" mention.
_OBLAST_MARKERS = ("област", "обл.")


def parse_alert_message(text: str) -> ParsedAlert | None:
    """Real тривога/відбій announcement -> scope, action and (since 06.09.2026)
    the threat level, else None (city news, weekly recaps, aftermath reports —
    the majority of this channel's traffic). відбій/all-clear is checked BEFORE
    start, since the відбій body names "оголошення тривоги" in a conditional.
    """
    low = text.lower()
    headline = _headline(low)

    if _END_RE.search(headline) or _END_EN_RE.search(headline):
        return ParsedAlert(scope=_scope(low), action="end")

    if _DECLARED_RE.search(headline):
        for pattern, level, threat in _THREATS:
            if pattern.search(headline):
                return ParsedAlert(scope=_scope(low), action="start",
                                   level=level, threat=threat)
    if _START_EN_RE.search(headline):
        return ParsedAlert(scope=_scope(low), action="start")

    return None


def _headline(low: str) -> str:
    for line in low.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _scope(low: str) -> str:
    return "oblast" if any(m in low for m in _OBLAST_MARKERS) else "city"

"""Reading an aftermath message: what happened to a place after a strike.

The parser already recognises this class — `rules._aftermath` — and then throws
it away, raions included (`rules.clears_districts`). This module is the other
half: given the same text, what the report is ABOUT and whether it is worth
placing at all. It decides nothing about suppression; a message that reaches
here is suppressed either way.

Pure and synchronous on purpose. The one part of the gate that needs the DB —
"is there a live incident in this region" — belongs to the ingest handler that
has a session; this module hands it `mentions_strike` and lets it decide.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import AFTERMATH_CATEGORIES
from ..parsing.matcher import normalize
from ..parsing.vocab import (
    _CAT_CASUALTIES,
    _CAT_DAMAGE,
    _CAT_FIRE,
    _CAT_RESCUE,
    _NOT_AN_AFTERMATH,
    _STRIKE_WORD,
    _STRIKE_WORD_VETO,
    _STRUCTURE_HARM_RE,
)

# Least → most consequential, so the tail is the label a marker takes. Derived
# from the enum rather than re-listing it, so a new category cannot be added
# without a place in this order.
_SEVERITY: tuple[str, ...] = ("damage", "fire", "rescue", "casualties")
assert set(_SEVERITY) == set(AFTERMATH_CATEGORIES), "every category needs a severity rank"

_WORDS: dict[str, tuple[str, ...]] = {
    "casualties": _CAT_CASUALTIES,
    "rescue": _CAT_RESCUE,
    "fire": _CAT_FIRE,
    "damage": _CAT_DAMAGE,
}


@dataclass(frozen=True)
class AftermathReading:
    """What one aftermath message says. `categories` is ordered least → most
    consequential, so `categories[-1]` is the label the display reads — a
    derived value, deliberately NOT stored on the row."""

    categories: list[str]
    # Whether the text itself names an attack. False does not mean "don't
    # record": the caller may still record it on the strength of a live incident
    # in the region. See the module docstring for why that split exists.
    mentions_strike: bool


def read_aftermath(text: str) -> AftermathReading | None:
    """The reading of `text`, or None when nothing should be recorded from it.

    None on two counts: the text is one of the look-alike classes that is not an
    aftermath at all (`_NOT_AN_AFTERMATH` — an announced controlled demolition,
    the rescue service's ordinary peacetime work), or no category matched, which
    means `_AFTERMATH` fired on a word this module cannot place.
    """
    norm = normalize(text)
    if any(w in norm for w in _NOT_AN_AFTERMATH):
        return None
    categories = categorize(norm)
    if not categories:
        return None
    return AftermathReading(categories=categories, mentions_strike=_mentions_strike(norm))


def categorize(norm: str) -> list[str]:
    """Every category the NORMALIZED text names, ordered least → most
    consequential. Multi-label because the data is: 7 of the 22 real reports
    name two at once («рятувальники деблокували тіло загиблого»)."""
    hits = {cat for cat in _SEVERITY if any(w in norm for w in _WORDS[cat])}
    # A building can «постраждати» too — see _STRUCTURE_HARM_RE. It reads as
    # damage, and the casualties reading is withdrawn only when «постраждал» was
    # the ONLY thing carrying it: «двоє людей постраждали… сталися пожежі, у
    # Святошинському постраждала будівля» is both at once, and dropping
    # casualties there would understate the message.
    if _STRUCTURE_HARM_RE.search(norm):
        hits.add("damage")
        if not any(w in norm for w in _CAT_CASUALTIES if w != "постраждал"):
            hits.discard("casualties")
    return [cat for cat in _SEVERITY if cat in hits]


def _mentions_strike(norm: str) -> bool:
    """Whether the text says this is about an attack.

    The veto matters more than it looks: «вибухонебезпечних предметів» contains
    «вибух», and it is the wording of the announced demolition that
    `_NOT_AN_AFTERMATH` exists to reject — so without it this gate would wave
    through exactly the class the layer must not place.
    """
    if any(w in norm for w in _STRIKE_WORD_VETO):
        return False
    return any(w in norm for w in _STRIKE_WORD)

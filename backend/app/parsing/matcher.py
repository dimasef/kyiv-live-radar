"""Text normalization, stemming, and per-district regex matching."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..gazetteer import CITYWIDE_NAME_EN as _CITYWIDE_NAME_EN
from .vocab import _APOSTROPHES, _STREET_WORDS, _SUFFIXES


def normalize(text: str) -> str:
    """Lowercase and unify apostrophes; keep letters, digits, emoji, spaces."""
    t = text.lower()
    for ch in _APOSTROPHES:
        t = t.replace(ch, "")
    return t


def _stem(word: str) -> str:
    w = normalize(word).replace(" ", "")
    for suf in _SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    return w


@dataclass
class DistrictHit:
    district_id: int
    name: str
    position: int  # char offset of the match (used to order a moving track)
    stem_len: int = 0  # length of the matched stem (specificity, for dedup)


def _is_street_reference(norm_text: str, start: int, end: int) -> bool:
    """True if the district-stem match at [start:end) is really part of a
    street name ("Оболонський проспект"), judged by the immediately adjacent
    word on either side."""
    before = norm_text[:start].rstrip(" ,.;:()–—-")
    after = norm_text[end:].lstrip(" ,.;:()–—-")
    before_word = before.rsplit(" ", 1)[-1] if before else ""
    after_word = after.split(" ", 1)[0] if after else ""
    return any(w in before_word for w in _STREET_WORDS) or any(
        w in after_word for w in _STREET_WORDS
    )


# Adjectives that turn a "море/моря/морі" match into a NON-Kyiv sea — a
# launch-zone / geopolitics mention ("Каспійського моря", "Чорного моря"), not
# the Kyiv Reservoir's "район моря" northern approach. Only these seas show up
# in the real spotter/strategic-report corpus; extend if a new one appears.
_FOREIGN_SEA_ADJ = ("каспійськ", "чорн", "азовськ", "балтійськ", "середземн", "мармуров")


def _is_foreign_sea(norm_text: str, start: int, end: int) -> bool:
    """True if a море/моря/морі match at [start:end) is really a foreign sea
    (preceded by a foreign-sea adjective), so it must NOT resolve to the Kyiv
    "Район моря" approach. Only ever fires on the море-family token — no other
    district stem starts with 'мор'."""
    if norm_text[start:end][:3] != "мор":
        return False
    before = norm_text[:start].rstrip(" ,.;:()–—-")
    before_word = before.rsplit(" ", 1)[-1] if before else ""
    return any(before_word.startswith(a) for a in _FOREIGN_SEA_ADJ)


class DistrictMatcher:
    """Compiles per-district stem regexes from names + aliases for fast matching."""

    def __init__(self, districts):
        # districts: iterable of objects/dicts with id, name_uk, aliases
        self._patterns: list[tuple[int, str, re.Pattern]] = []
        # (id, name) index — the allowed district set for the LLM fallback.
        self.districts_index: list[tuple[int, str]] = []
        for d in districts:
            did = d["id"] if isinstance(d, dict) else d.id
            name = d["name_uk"] if isinstance(d, dict) else d.name_uk
            name_en = d["name_en"] if isinstance(d, dict) else getattr(d, "name_en", "")
            aliases = (d["aliases"] if isinstance(d, dict) else d.aliases) or []
            # The city-wide sentinel is not a real matchable place — skip it
            # entirely (both stem matching and the LLM's allowed-id index) so a
            # bare "київ" never resolves to it and the LLM can't pick it.
            if name_en == _CITYWIDE_NAME_EN:
                continue
            self.districts_index.append((did, name))
            stems = set()
            for form in [name, *aliases]:
                s = _stem(form)
                if len(s) >= 4:
                    stems.add(s)
            if not stems:
                continue
            # Word-start boundary + stem + optional Ukrainian tail (case endings).
            alt = "|".join(sorted(map(re.escape, stems), key=len, reverse=True))
            pat = re.compile(r"(?<![а-яіїєґ])(?:" + alt + r")[а-яіїєґ]*", re.IGNORECASE)
            self._patterns.append((did, name, pat, max(len(s) for s in stems)))

    def find(self, norm_text: str) -> list[DistrictHit]:
        hits: dict[int, DistrictHit] = {}
        for did, name, pat, stem_len in self._patterns:
            for m in pat.finditer(norm_text):
                if _is_street_reference(norm_text, m.start(), m.end()):
                    continue
                if _is_foreign_sea(norm_text, m.start(), m.end()):
                    continue
                hits[did] = DistrictHit(did, name, m.start(), stem_len)
                break
        # Resolve prefix overlaps (e.g. Оболонь vs Оболонський matching the same
        # word): among hits at the same start offset, keep the most specific
        # (longest stem) and drop the rest.
        by_start: dict[int, DistrictHit] = {}
        for h in hits.values():
            cur = by_start.get(h.position)
            if cur is None or h.stem_len > cur.stem_len:
                by_start[h.position] = h
        return sorted(by_start.values(), key=lambda h: h.position)

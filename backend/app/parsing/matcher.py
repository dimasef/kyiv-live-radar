"""Text normalization, stemming, and per-district regex matching."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..gazetteer import CITYWIDE_NAME_EN as _CITYWIDE_NAME_EN
from ..gazetteer import HOME_REGION as _HOME_REGION
from .vocab import (
    _ALIAS_NEXT_WORD_VETO,
    _ALIAS_PREV_WORD_REQUIRED,
    _APOSTROPHES,
    _OBLAST_CITY_STEMS,
    _STREET_WORDS,
    _SUFFIXES,
    _WHOLE_WORD_ALIASES,
)


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


# Punctuation to skip when looking at the word next to a match. The quote marks
# matter: spotters quote landmark names («метро "Чернігівська"»), and without
# them the "adjacent word" is the quote character, so every context veto below
# silently fails on exactly the phrasings it exists for.
_EDGE = " ,.;:()–—-«»\"'„“”"


def _is_street_reference(norm_text: str, start: int, end: int) -> bool:
    """True if the district-stem match at [start:end) is really part of a
    street name ("Оболонський проспект"), judged by the immediately adjacent
    word on either side."""
    before = norm_text[:start].rstrip(_EDGE)
    after = norm_text[end:].lstrip(_EDGE)
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
    before = norm_text[:start].rstrip(_EDGE)
    before_word = before.rsplit(" ", 1)[-1] if before else ""
    return any(before_word.startswith(a) for a in _FOREIGN_SEA_ADJ)


# Word endings that turn a CITY's stem into its OBLAST ("Чернігів" ->
# "Чернігівщина"/"Чернігівська область", "Суми" -> "Сумщина"). The stemmer can't
# tell them apart — «чернігів» plus a free case tail swallows both — but the two
# mean different things here: the city is a place a target can be OVER, the
# oblast is almost always where one came FROM, which the directional-axis layer
# owns (domain/origins.py). Pinning "з Чернігівщини курсом на Київ" to the city
# centre would turn every northern axis into a phantom sighting 130 km away.
#
# Only the -щина family is checked by shape; the adjectival form is recognized
# by the word that FOLLOWS it, because Kyiv's own raions are adjectives too
# ("Оболонський", "Дарницький") and must keep matching.
_OBLAST_SUFFIX = "щин"
_OBLAST_NEXT = ("област", "обл")


def _is_oblast_form(norm_text: str, start: int, end: int, stem: str) -> bool:
    """True if the match at [start:end) is the OBLAST form of a city's name.

    Judged on the CASE TAIL, never on the whole word: «Троєщина» and
    «Вигурівщина» are places whose own stem ends in -щин, and vetoing those
    would take out the most-named raion on the map.
    """
    # `in`, not `startswith`: the stemmer already ate part of the city's own
    # ending («Чернігів» stems to «черніг»), so the oblast marker sits mid-tail
    # — "чернігівщини" leaves "івщини".
    tail = norm_text[start + len(stem):end]
    if _OBLAST_SUFFIX in tail:
        return True
    # For a city that shares its name with an oblast, the adjectival form is
    # the oblast even with «область» left out («мандрує Чернігівською»).
    if stem in _OBLAST_CITY_STEMS and "ськ" in tail:
        return True
    after = norm_text[end:].lstrip(_EDGE)
    next_word = after.split(" ", 1)[0] if after else ""
    return next_word.startswith(_OBLAST_NEXT)


def _is_proper_name(norm_text: str, start: int, end: int) -> bool:
    """True if the match at [start:end) is part of a proper name that merely
    contains a toponym alias ("Голос Києва", a channel) — see
    vocab._ALIAS_NEXT_WORD_VETO."""
    veto = _ALIAS_NEXT_WORD_VETO.get(norm_text[start:end])
    if not veto:
        return False
    after = norm_text[end:].lstrip(_EDGE)
    next_word = after.split(" ", 1)[0] if after else ""
    return next_word.startswith(veto)


def _missing_required_prev(norm_text: str, start: int, end: int) -> bool:
    """True if the match at [start:end) needs a specific preceding word and
    doesn't have it ("церкв" only counts inside "Біла Церква") — see
    vocab._ALIAS_PREV_WORD_REQUIRED."""
    matched = norm_text[start:end]
    for alias, required in _ALIAS_PREV_WORD_REQUIRED.items():
        if not matched.startswith(alias):
            continue
        before = norm_text[:start].rstrip(_EDGE)
        prev_word = before.rsplit(" ", 1)[-1] if before else ""
        return not prev_word.startswith(required)
    return False


class DistrictMatcher:
    """Compiles per-district stem regexes from names + aliases for fast matching.

    `prefer_region` breaks ties between genuine homonyms across the oblast
    border — Лебедівка, Рокитне and Дніпровське all exist in BOTH Київська and
    Чернігівська область, and nothing in the text tells them apart. The
    reporting channel does: a northern spotter calling «Лебедівка на
    гончарівське» means the one next to Гончарівське, not the Vyshhorod-district
    village 60 km away. Callers pass the source's region (see
    feeds/common.RegionMatchers); with None, whichever entry comes first in the
    gazetteer wins, exactly as before.

    `region_only` on an entry is the stronger form: that place is matchable ONLY
    by a channel reporting from its own region, and is invisible (stem index AND
    LLM enum) to every other one. It exists for the generic city landmarks both
    oblasts share — «ТЕЦ», «вокзал», «летовище», «очисні» name a real, specific
    point to the spotters watching one city and a different one 150 km away.
    `prefer_region` cannot help there: it only breaks TIES, and a lone entry
    faces no tie, so a Chernihiv «ТЕЦ» would have claimed all 42 Kyiv mentions
    of theirs. With `prefer_region=None` the home region's entries are the ones
    kept, matching HOME_REGION's role as the default for anything unstated.
    """

    def __init__(self, districts, prefer_region: str | None = None):
        # districts: iterable of objects/dicts with id, name_uk, aliases
        self._patterns: list[tuple[int, str, re.Pattern, bool]] = []
        # (id, name) index — the allowed district set for the LLM fallback.
        self.districts_index: list[tuple[int, str]] = []
        # id -> region, so the LLM prompt can label each allowed place (a name
        # alone can't tell the model which side of the oblast border it is on).
        self.region_by_id: dict[int, str] = {}
        self.prefer_region = prefer_region
        for d in districts:
            did = d["id"] if isinstance(d, dict) else d.id
            name = d["name_uk"] if isinstance(d, dict) else d.name_uk
            name_en = d["name_en"] if isinstance(d, dict) else getattr(d, "name_en", "")
            aliases = (d["aliases"] if isinstance(d, dict) else d.aliases) or []
            region = (d.get("region") if isinstance(d, dict) else getattr(d, "region", None))
            # The city-wide sentinel is not a real matchable place — skip it
            # entirely (both stem matching and the LLM's allowed-id index) so a
            # bare "київ" never resolves to it and the LLM can't pick it.
            if name_en == _CITYWIDE_NAME_EN:
                continue
            # A region-exclusive entry belongs to no other region's matcher at
            # all — dropped before the index, so the LLM can't pick it either.
            region_only = bool(
                d.get("region_only") if isinstance(d, dict) else getattr(d, "region_only", False)
            )
            if region_only and region != (prefer_region or _HOME_REGION):
                continue
            self.districts_index.append((did, name))
            if region:
                self.region_by_id[did] = region
            stems, exact = set(), set()
            for form in [name, *aliases]:
                if normalize(form).replace(" ", "") in _WHOLE_WORD_ALIASES:
                    exact.add(normalize(form).replace(" ", ""))
                    continue
                s = _stem(form)
                if len(s) >= 4:
                    stems.add(s)
            if not stems and not exact:
                continue

            def _alt(forms):
                return "|".join(sorted(map(re.escape, forms), key=len, reverse=True))

            # Word-start boundary + stem + optional Ukrainian tail (case endings).
            # The stem is captured so `find` can rank a hit by how much of the
            # WORD it actually explained — see the overlap resolution there.
            branches = []
            if stems:
                branches.append(r"(?P<stem>" + _alt(stems) + r")[а-яіїєґ]*")
            # A short abbreviation carries no case tail, so it matches as a whole
            # word only ("ЧЗВ") — see _WHOLE_WORD_ALIASES.
            if exact:
                branches.append(r"(?P<word>" + _alt(exact) + r")(?![а-яіїєґ])")
            pat = re.compile(r"(?<![а-яіїєґ])(?:" + "|".join(branches) + r")", re.IGNORECASE)
            preferred = prefer_region is not None and region == prefer_region
            self._patterns.append((did, name, pat, preferred))

    def find(self, norm_text: str) -> list[DistrictHit]:
        hits: dict[int, tuple[DistrictHit, bool]] = {}
        for did, name, pat, preferred in self._patterns:
            for m in pat.finditer(norm_text):
                groups = m.groupdict()
                matched = groups.get("stem") or groups.get("word") or m.group(0)
                if _is_street_reference(norm_text, m.start(), m.end()):
                    continue
                if _is_foreign_sea(norm_text, m.start(), m.end()):
                    continue
                if _is_oblast_form(norm_text, m.start(), m.end(), matched):
                    continue
                if _is_proper_name(norm_text, m.start(), m.end()):
                    continue
                if _missing_required_prev(norm_text, m.start(), m.end()):
                    continue
                hits[did] = (DistrictHit(did, name, m.start(), len(matched)), preferred)
                break
        # Resolve prefix overlaps (e.g. Оболонь vs Оболонський matching the same
        # word): among hits at the same start offset, keep the most specific
        # (longest MATCHED stem) and drop the rest.
        #
        # It has to be the stem that actually fired, not the entry's longest
        # stem: an entry with one short alias would otherwise claim the
        # specificity of its longest one and win overlaps it has no business
        # winning. Live example — «Морівськ» (a Chernihiv village) lost to
        # «Район моря», whose 4-letter alias «морі» is a prefix of it but which
        # advertised the 8 of «районмор», pinning a village 60 km onto the Kyiv
        # reservoir. Ranking by the whole match doesn't help either: the case
        # tail `[а-яіїєґ]*` swallows the rest of the word for both.
        #
        # Specificity first, `prefer_region` only as the tie-break: two entries
        # that explain the same amount of the word are true homonyms
        # (Лебедівка/Рокитне/Дніпровське exist on both sides of the oblast
        # border), and there the reporting channel's own region is the only
        # evidence available.
        by_start: dict[int, tuple[DistrictHit, bool]] = {}
        for hit, preferred in hits.values():
            cur = by_start.get(hit.position)
            if cur is None or (hit.stem_len, preferred) > (cur[0].stem_len, cur[1]):
                by_start[hit.position] = (hit, preferred)
        return sorted((h for h, _ in by_start.values()), key=lambda h: h.position)

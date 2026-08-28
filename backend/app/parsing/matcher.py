"""Text normalization, stemming, and per-district regex matching."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..gazetteer import CITYWIDE_NAME_EN as _CITYWIDE_NAME_EN
from ..regions import HOME_REGION as _HOME_REGION
from .vocab import (
    _ALIAS_NEXT_WORD_REQUIRED,
    _ALIAS_NEXT_WORD_VETO,
    _ALIAS_PREV_WORD_REQUIRED,
    _ALIAS_PREV_WORD_VETO,
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
    # Char offset just past the WHOLE match, case tail included. Needed by the
    # count rules to tell «Замглай два» (two targets over Замглай) from «ТЕЦ-5»
    # (a plant's number, part of the name) — `position + stem_len` cannot: the
    # stem is only the part of the word the entry explained.
    end: int = 0


# Punctuation to skip when looking at the word next to a match. The quote marks
# matter: spotters quote landmark names («метро "Чернігівська"»), and without
# them the "adjacent word" is the quote character, so every context veto below
# silently fails on exactly the phrasings it exists for.
_EDGE = " ,.;:()–—-«»\"'„“”"


# Punctuation that ENDS a callout: whatever follows it is the next item in the
# list, not part of this name. A street word reached across one of these is a
# different place being named, so the veto below must not see it — «Суми,
# Проспект Перемоги» is two locations, and treating the second as an adjacent
# word made the first one a street reference (2026-08-28).
#
# Quote marks are deliberately NOT here. They WRAP a name rather than end it —
# «метро "Бориспільська"» is one phrase — and treating them as a break took the
# veto off exactly the quoted-landmark phrasing `_EDGE` above exists for.
_LIST_BREAK = ",;/|\n>"


def _is_street_reference(norm_text: str, start: int, end: int,
                         is_street_name: bool = False) -> bool:
    """True if the district-stem match at [start:end) is really part of a
    street name ("Оболонський проспект"), judged by the immediately adjacent
    word on either side.

    `is_street_name` exempts an entry that IS a street or a square («Проспект
    Перемоги», «Вокзальна площа»): for those the street word is the other half
    of their own name, so the veto fires on exactly the phrasing they exist for.
    """
    if is_street_name:
        return False
    # The break is looked for BEFORE `_EDGE` is stripped — stripping first would
    # eat the comma that says the neighbour is a separate callout. Only spaces
    # are skipped on the way to it.
    if norm_text[:start].rstrip(" ")[-1:] in _LIST_BREAK:
        before_word = ""
    else:
        before = norm_text[:start].rstrip(_EDGE)
        before_word = before.rsplit(" ", 1)[-1] if before else ""
    if norm_text[end:].lstrip(" ")[:1] in _LIST_BREAK:
        after_word = ""
    else:
        after = norm_text[end:].lstrip(_EDGE)
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


# Gazetteer names that are ALSO the name of a Russian strategic-bomber base.
# «Українка» is a town in Обухівський р-н, 40 km south of Kyiv, AND the Amur
# Oblast base the Ту-95МС/Ту-160 fly from — and the strategic reports name the
# base more often than the spotters name the town (20+ stored posts against 11
# real callouts). Matched by STEM, so this is the stem, not the name.
_AIRBASE_HOMONYM_STEMS = ("українк",)

# What marks the whole message as one of those reports. The adjacent word is not
# enough on its own: the channel writes «з ае. «Українка»» (abbreviated), lists
# two bases off one preposition («з аеродромів «Оленья» та «Українка»»), and
# sometimes names the base by context alone («передислоковані сьогодні з
# Українки на Оленью»). What every one of them DOES carry is the vocabulary of
# strategic aviation — a bomber type or another base — while not one of the 11
# real town callouts does.
#
# Stems, not words: the base names decline too («на Оленью», «з Оленьї»), and
# «передислоковані» is the same report as «передислокація». Being generous costs
# nothing here — the veto only ever looks at a message that already named
# Українка, and no real callout of the town carries any of this vocabulary.
_AIRBASE_CONTEXT = (
    "аеродром", "авіабаз", "ае.", "олень", "оленя", "енгельс", "енгельм",
    "дягилево", "шайковк", "борисоглєбск", "белая", "ту-95", "ту95", "ту-160",
    "ту160", "ту-22", "ту22", "тушк", "бомбардувальник", "передислок",
    "пускові рубежі",
)


def _is_airbase_reference(norm_text: str, start: int, end: int) -> bool:
    """True if a match at [start:end) is the NAME OF A RUSSIAN AIRBASE rather
    than the Kyiv-oblast town it shares a name with.

    Scoped to the stems that actually have that problem (as `_is_foreign_sea`
    scopes itself to the море-family token), and judged on the WHOLE message
    rather than the adjacent word — see `_AIRBASE_CONTEXT` for why the adjacent
    word is not enough. Without this veto the entry cannot exist: every Ту-95
    take-off would draw a live target south of Kyiv."""
    if not norm_text[start:end].startswith(_AIRBASE_HOMONYM_STEMS):
        return False
    return any(w in norm_text for w in _AIRBASE_CONTEXT)


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


def _missing_required_next(norm_text: str, start: int, end: int) -> bool:
    """True if the match at [start:end) needs a specific FOLLOWING word and
    doesn't have it («старе» only counts before «село») — see
    vocab._ALIAS_NEXT_WORD_REQUIRED."""
    matched = norm_text[start:end]
    for alias, required in _ALIAS_NEXT_WORD_REQUIRED.items():
        if not matched.startswith(alias):
            continue
        after = norm_text[end:].lstrip(_EDGE)
        next_word = after.split(" ", 1)[0] if after else ""
        return not next_word.startswith(required)
    return False


def _has_vetoed_prev(norm_text: str, start: int, end: int) -> bool:
    """True if the match at [start:end) is disqualified by the word before it
    («Велика Писарівка» is not Писарівка) — see vocab._ALIAS_PREV_WORD_VETO."""
    matched = norm_text[start:end]
    for alias, veto in _ALIAS_PREV_WORD_VETO.items():
        if not matched.startswith(alias):
            continue
        before = norm_text[:start].rstrip(_EDGE)
        prev_word = before.rsplit(" ", 1)[-1] if before else ""
        return prev_word.startswith(veto)
    return False


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


def _visible_to(
    prefer_region: str | None, allowed: frozenset[str] | None, region: str | None
) -> bool:
    """Whether an entry of `region` is matchable by this matcher.

    With `allowed` given (the regions a SOURCE is bound to), that set is the
    whole answer and it applies to every source alike, the home region
    included — a channel never pins a place outside what it was bound to.

    With `allowed` None the older asymmetric rule stands: the home region (and
    an unspecified one) sees everything, every other region sees only its own.
    That path is still what the admin, coverage and reprocess tools use, where
    there is no one source to read a binding off.

    An entry with no region of its own is home-region by default, which is what
    makes the whole Kyiv gazetteer invisible to a northern matcher without
    touching a single row.
    """
    own = region or _HOME_REGION
    if allowed is not None:
        return own in allowed
    if prefer_region is None or prefer_region == _HOME_REGION:
        return True
    return own == prefer_region


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

    Visibility is ASYMMETRIC: a channel outside the home region sees ONLY its
    own region's entries, while a home-region channel keeps seeing everything.
    That is not symmetry for its own sake — it is what the traffic looks like.
    Kyiv channels legitimately narrate the northern approach (68 stored events
    over Chernihiv districts); the northern channel never reports a Kyiv place
    correctly, and all 10 of its stored Kyiv-district events were false matches
    on a longer northern name («Мезин, деснянське» -> Деснянський РАЙОН of Kyiv,
    «На Оболоння на короп» -> Оболонь, «Чайкине на жадове» -> Чайки). Those cost
    more than a wrong pin: the district's region is what a track inherits, so a
    mis-match promotes a northern blip into a Kyiv track, a Kyiv incident and a
    "attack finished" card (incident 208, 2026-08-22). Measured over all 926
    northern messages, the rule changes 4 of them and every one is a fix.

    A target that genuinely crosses into Kyiv oblast still hands over normally —
    the Kyiv channels are the ones that call it in (handlers._hand_over_region).
    If the northern channel ever names a Kyiv place, the message stays
    unlocalized and surfaces in the admin coverage-gap queue, which is visible
    rather than silent.
    """

    def __init__(
        self,
        districts,
        prefer_region: str | None = None,
        allowed_regions: frozenset[str] | None = None,
    ):
        # districts: iterable of objects/dicts with id, name_uk, aliases
        self._patterns: list[tuple[int, str, re.Pattern, bool, bool]] = []
        # (id, name) index — the allowed district set for the LLM fallback.
        self.districts_index: list[tuple[int, str]] = []
        # id -> region, so the LLM prompt can label each allowed place (a name
        # alone can't tell the model which side of the oblast border it is on).
        self.region_by_id: dict[int, str] = {}
        self.prefer_region = prefer_region
        self.allowed_regions = allowed_regions
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
            # …and OUTSIDE the home region every entry behaves that way: a
            # northern channel is shown northern places only (see the class
            # docstring for the measurement).
            if not _visible_to(prefer_region, allowed_regions, region):
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
            # An entry that IS a street or a square is exempt from the street
            # veto — see _is_street_reference.
            is_street_name = any(w in normalize(name) for w in _STREET_WORDS)
            self._patterns.append((did, name, pat, preferred, is_street_name))

    def find(self, norm_text: str) -> list[DistrictHit]:
        hits: dict[int, tuple[DistrictHit, bool]] = {}
        for did, name, pat, preferred, is_street_name in self._patterns:
            for m in pat.finditer(norm_text):
                groups = m.groupdict()
                matched = groups.get("stem") or groups.get("word") or m.group(0)
                if _is_street_reference(norm_text, m.start(), m.end(), is_street_name):
                    continue
                if _is_foreign_sea(norm_text, m.start(), m.end()):
                    continue
                if _is_airbase_reference(norm_text, m.start(), m.end()):
                    continue
                if _is_oblast_form(norm_text, m.start(), m.end(), matched):
                    continue
                if _is_proper_name(norm_text, m.start(), m.end()):
                    continue
                if _missing_required_prev(norm_text, m.start(), m.end()):
                    continue
                if _has_vetoed_prev(norm_text, m.start(), m.end()):
                    continue
                if _missing_required_next(norm_text, m.start(), m.end()):
                    continue
                hits[did] = (
                    DistrictHit(did, name, m.start(), len(matched), m.end()), preferred)
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

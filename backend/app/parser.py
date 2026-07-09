"""Rule-based parser: raw Ukrainian channel text -> structured event.

This is the primary parsing layer (spec §5): cheap, instant, no network. It
recognizes target type, status, and mentioned districts. Ambiguous / unmatched
text is where the optional LLM fallback (Claude Haiku 4.5) plugs in later — this
module deliberately returns low confidence and empty districts rather than
guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- Target type keywords (checked in priority order) ---
# Missile first: it's the most time-critical and must not be shadowed by a
# generic "drone" mention in the same message.
_MISSILE = ("ракет", "баліст", "крилат", "калібр", "кинджал", "іскандер",
            "х-101", "х-59", "х-22", "каб", "авіабомб", "керован авіа")
_JET = ("реактивн", "швидкісн", "реактивного бпла")
_SHAHED = ("шахед", "shahed", "мопед", "герань", "герані", "дрон", "бпла",
           "безпілотник", "безпілотн")

# --- Status keywords ---
_CLEAR = ("відбій",)
# "мінус" = spotter shorthand for a downed target ("Мінус", "мінус ще один") —
# the common destroyed-terminal on «Місто Кия | Безпека»; substring-safe in this
# feed (threat context, not weather/temperature).
_DESTROYED = ("збил", "збито", "знищ", "нейтраліз", "уражен", "ліквідов", "впав",
              "мінус")
_UNCONFIRMED = ("уточнюється", "непідтвердж", "не підтвердж", "попередньо", "можливо")
_CONFIRMED = ("підтвердж", "🔴")

# --- New-target markers (start a fresh track) ---
_NEW_TARGET = ("новий", "нова ціль", "ще один", "ще одна", "інша ціль",
               "друга ціль", "додатков", "нові цілі")

# Explicit target-count shorthand spotters use: "2х", "їх вже 3х" (a number then
# х/x). The negative lookahead drops "20хв"=minutes and any number glued to a
# word. This is the stated size of a group flying together — one reply-chain
# track carries the whole group, so the count annotates the track (viz), it does
# NOT fabricate N separate tracks.
_COUNT_RE = re.compile(r"(\d+)\s*[хx](?![а-яіїєґa-z])", re.IGNORECASE)

# --- Aftermath / consequence vocabulary. A message describing the RESULT of a
# strike (casualties, damage, rescue) is NEWS about a place, not a live target
# to track — even if it names a district. These suppress a sighting. ---
_AFTERMATH = ("постраждал", "загинул", "поранен", "жертв", "уламк", "пошкодж",
              "зруйнов", "врятув", "рятувальник", "надзвичайник", "дснс",
              "багатоповерхів", "наслідк", "кмва", "госпіталіз", "медик",
              "евакуй", "загибл", "потерпіл")

# Case endings stripped (longest first) to reduce a Ukrainian word to a rough
# stem, so one stem regex matches most forms (Троєщина/Троєщині/Троєщину).
# IMPORTANT: we deliberately keep the adjectival "-ськ/-цьк" root (strip only
# "ий"/"ого"/"их" after it), so a raion adjective (Оболонський) stays distinct
# from the same-root noun (Оболонь) instead of collapsing to a shared stem.
_SUFFIXES = ("ого", "ому", "ій", "ої", "ою", "их", "ий", "им", "ах", "ям",
             "ам", "ів", "ь", "и", "а", "я", "у", "ю", "і", "е", "о")

_APOSTROPHES = "'ʼ`’‘"


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


@dataclass
class ParseResult:
    target_type: str  # 'shahed' | 'jet_drone' | 'missile' | 'unknown'
    status: str       # 'confirmed' | 'sighting' | 'unconfirmed' | 'destroyed' | 'clear'
    is_new_target: bool
    districts: list[DistrictHit]
    confidence: float
    target_count: int | None = None  # stated group size ("2х"), None if unstated
    raw_text: str = ""
    matched: bool = field(default=False)
    aftermath: bool = field(default=False)


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
            aliases = (d["aliases"] if isinstance(d, dict) else d.aliases) or []
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
            m = pat.search(norm_text)
            if m and did not in hits:
                hits[did] = DistrictHit(did, name, m.start(), stem_len)
        # Resolve prefix overlaps (e.g. Оболонь vs Оболонський matching the same
        # word): among hits at the same start offset, keep the most specific
        # (longest stem) and drop the rest.
        by_start: dict[int, DistrictHit] = {}
        for h in hits.values():
            cur = by_start.get(h.position)
            if cur is None or h.stem_len > cur.stem_len:
                by_start[h.position] = h
        return sorted(by_start.values(), key=lambda h: h.position)


# Some keywords are short abbreviations that collide with common words (e.g.
# "каб" inside "кабель"/"кабіна"). Match those as whole words; match everything
# else at a word start so inflected suffixes still hit (ракет→ракети).
_WHOLE_WORD = {"каб"}


def _kw_regex(words) -> re.Pattern:
    parts = []
    for w in words:
        esc = re.escape(w)
        if w in _WHOLE_WORD:
            parts.append(r"(?<![а-яіїєґ])" + esc + r"(?![а-яіїєґ])")
        else:
            parts.append(r"(?<![а-яіїєґ])" + esc)
    return re.compile("|".join(parts))


_MISSILE_RE = _kw_regex(_MISSILE)
_JET_RE = _kw_regex(_JET)
_SHAHED_RE = _kw_regex(_SHAHED)


def _target_type(norm: str) -> str:
    if _MISSILE_RE.search(norm):
        return "missile"
    if _JET_RE.search(norm):
        return "jet_drone"
    if _SHAHED_RE.search(norm):
        return "shahed"
    return "unknown"


def _target_count(norm: str) -> int | None:
    """The largest sane group count stated in the text ("2х" -> 2), else None."""
    nums = [int(m.group(1)) for m in _COUNT_RE.finditer(norm)]
    nums = [n for n in nums if 1 <= n <= 50]  # ignore junk like "100х"/years
    return max(nums) if nums else None


def _status(text: str, norm: str) -> tuple[str, float]:
    """Return (status, base_confidence)."""
    if any(k in norm for k in _CLEAR):
        return "clear", 0.9
    if any(k in norm for k in _DESTROYED):
        return "destroyed", 0.85
    if any(k in norm for k in _UNCONFIRMED):
        return "unconfirmed", 0.35
    if "🔴" in text or any(k in norm for k in _CONFIRMED):
        return "confirmed", 0.9
    return "sighting", 0.6


def parse_message(text: str, matcher: DistrictMatcher) -> ParseResult:
    norm = normalize(text)
    target_type = _target_type(norm)
    status, conf = _status(text, norm)
    is_new = any(k in norm for k in _NEW_TARGET)
    target_count = _target_count(norm)
    districts = matcher.find(norm)

    # Aftermath/consequence news ("постраждала багатоповерхівка", "врятували
    # дитину") mentions a district but is NOT a live target — suppress it, unless
    # it's an all-clear (which legitimately closes tracks).
    aftermath = any(k in norm for k in _AFTERMATH) and status != "clear"

    # No district and no actionable status -> nothing structured to record.
    matched = (bool(districts) or status in ("clear", "destroyed")) and not aftermath
    if aftermath:
        districts = []
    # Confidence drops when we can't localize the target.
    if not districts and status not in ("clear",):
        conf = min(conf, 0.3)

    return ParseResult(
        target_type=target_type,
        status=status,
        is_new_target=is_new,
        districts=districts,
        confidence=round(conf, 2),
        target_count=target_count,
        raw_text=text,
        matched=matched,
        aftermath=aftermath,
    )

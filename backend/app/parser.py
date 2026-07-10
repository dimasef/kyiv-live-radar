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
              "евакуй", "загибл", "потерпіл",
              "пожеж",       # "пожежі на Трої" — fire footage is aftermath, not a sighting
              "відновленн")  # "виділить... на відновлення" — reconstruction-funding news

# --- Explicit denial that a target is at/heading to a place ("Не йде на
# Оболонь", "без загроз для Борисполя"). Curated phrases (not bare "не" — that
# would also swallow "не підтверджено" = unconfirmed, a different status
# entirely). LIMITATION: message-scoped — a negation anywhere in the message
# suppresses ALL its district hits, so a hypothetical single message that both
# denies one target AND reports a different live one would be wrongly dropped
# in full; no real example of that shape has been seen in the feed yet. ---
_NEGATION = ("не йде", "не летить", "не рухається", "не курсом", "не в бік",
             "не фіксується", "не спостерігається", "не зафіксовано",
             "без загроз", "поза загрозою")

# --- Siren-status announcement ("+ Бучанський район тривога", "Тривога у
# Вишгородському районі"). This is a technical "the siren went off in this
# district" notice — NOT a target sighting: it names a district but no target
# type (shahed/missile/jet) at all. A real sighting in this feed always states
# a type alongside the district ("2х реактивних в район Жукин"), so the
# compound signal (target unresolved + the "тривога" stem present) isolates
# the siren-echo cleanly without a shape-specific regex. ---
_SIREN_WORD = "тривог"

# --- Day-summary commentary ("Знову Деснянський район під атакою сьогодні")
# names a district but with no live target type/vector — a recap of the day
# rather than a fresh sighting. Unlike siren_only there's no clean marker that
# this ISN'T a real live report (the same "сьогодні" word can appear in an
# actual sighting too), so this only lowers confidence and keeps the
# district — safer than suppressing on a heuristic this soft. ---
_DAY_RECAP_WORD = "сьогодн"

# --- Political/official quote naming a place ("У Вишневому був склад
# боєприпасів... — Зеленський"). A news channel repeating a politician's or
# official's statement about a place is NOT a live spotter sighting, even
# though it names a district — distinct from siren_only/day_recap (those are
# about a real-time siren/recap, this is about WHO is speaking). Marker: the
# journalistic attribution convention of an em-dash (or plain dash) followed
# by a named official/institution, e.g. "— Зеленський", "- заявив президент".
# Swept the full real corpus (871 archived + live DB) for this shape: only 2
# real hits, both variants of the same Вишневе/Зеленський story — rare but a
# real, distinct false-positive class, so a small curated name list (same
# pattern as _NEGATION/_AFTERMATH) is proportionate; a broader "any dash +
# capitalized surname" regex would be far riskier without more real examples
# to validate against. ---
_QUOTE_ATTRIBUTION_RE = re.compile(
    r"[—-]\s*(президент\w*|зеленськ\w*|сирськ\w*|кличк\w*|ігнат\w*|умєров\w*|"
    r"буданов\w*|малюк\w*|генштаб\w*)",
    re.IGNORECASE,
)

# --- "Дорозвідка" — real air-defense terminology meaning our side no longer
# HAS/SEES targets of the stated type (or, if no type is named, no targets at
# all) and is re-scanning; a temporary stand-down, NOT "it was a harmless
# recon drone" (a dictionary-meaning trap — confirmed with the user). Message-
# scoped, no target type of its own to report, so a message that ALSO names a
# district (a genuine concurrent sighting of something else, e.g. "Дорозвідка
# по ракетах, залишаються БПЛА в районі Позняки") must NOT be swallowed — the
# compound gate below requires no district at all. Swept all 23 real
# occurrences in the corpus: 21 match this gate cleanly (no district), 1 has a
# district (correctly excluded), 1 already resolves via "відбій". ---
_LOST_WORD = "дорозвід"

# Case endings stripped (longest first) to reduce a Ukrainian word to a rough
# stem, so one stem regex matches most forms (Троєщина/Троєщині/Троєщину).
# IMPORTANT: we deliberately keep the adjectival "-ськ/-цьк" root (strip only
# "ий"/"ого"/"их" after it), so a raion adjective (Оболонський) stays distinct
# from the same-root noun (Оболонь) instead of collapsing to a shared stem.
_SUFFIXES = ("ого", "ому", "ій", "ої", "ою", "их", "ий", "им", "ах", "ям",
             "ам", "ів", "ь", "и", "а", "я", "у", "ю", "і", "е", "о")

_APOSTROPHES = "'ʼ`’‘"

# Street-name collision guard: a raion's adjectival form ("Оболонський",
# "Дарницький"...) is also used as part of an actual street name ("Оболонський
# проспект", "Дарницьке шосе") in utility/admin announcements ("промивка
# мереж по вулицях..."). Same bug class as the Остер/"остерігайтеся" stem
# collision — the fix here is contextual instead of dropping the toponym: a
# district-stem match immediately adjacent to one of these street-type nouns
# is a street reference, not a district mention, so DistrictMatcher discards
# it and keeps looking for another (real) occurrence in the same message.
_STREET_WORDS = ("проспект", "вулиц", "провулок", "бульвар", "узвіз", "шосе",
                  "набережн", "площ")


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
    negated: bool = field(default=False)
    siren_only: bool = field(default=False)
    day_recap: bool = field(default=False)
    political_quote: bool = field(default=False)
    lost_signal: bool = field(default=False)


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
            for m in pat.finditer(norm_text):
                if _is_street_reference(norm_text, m.start(), m.end()):
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

    # Explicit denial ("Не йде на Оболонь") mentions a district but says the
    # target is NOT there — suppress it, same carve-out as aftermath: an
    # explicit clear/destroyed keyword elsewhere in the message still wins (its
    # own keyword signal is stronger evidence than a coincidental negation word).
    negated = any(k in norm for k in _NEGATION) and status not in ("clear", "destroyed")

    # Siren-status echo: names a district, mentions "тривога", but states no
    # target type at all — the technical "alarm is on here" notice, not a
    # sighting. Only applies to sighting/confirmed statuses; an explicit
    # clear/destroyed keyword is still a real signal worth keeping.
    siren_only = (
        target_type == "unknown"
        and status in ("sighting", "confirmed")
        and bool(districts)
        and _SIREN_WORD in norm
    )

    # Day-summary commentary ("...під атакою сьогодні"): same shape as
    # siren_only (no target type at all), but "сьогодні" alone isn't a clean
    # enough marker to justify dropping the district outright, so this only
    # softens confidence instead of suppressing the sighting.
    day_recap = (
        target_type == "unknown"
        and status == "sighting"
        and bool(districts)
        and _DAY_RECAP_WORD in norm
    )
    if day_recap:
        conf = min(conf, 0.35)

    # Political/official quote naming a place, no stated target type — a news
    # repost of a statement, not a spotter sighting. Same shape-gate as
    # siren_only (target type unresolved + a district present); an explicit
    # target type stated elsewhere in the same message still wins.
    political_quote = (
        target_type == "unknown"
        and status in ("sighting", "confirmed")
        and bool(districts)
        and bool(_QUOTE_ATTRIBUTION_RE.search(norm))
    )

    # "Дорозвідка": ППО no longer has/sees targets of the stated type (or, if
    # unstated, no targets at all) — a real stand-down signal handled directly
    # by ingest.py (closes matching open tracks), not a suppression like the
    # flags above. Gate is deliberately just "no district" — see _LOST_WORD's
    # comment for why a district-bearing message must never match this.
    lost_signal = _LOST_WORD in norm and not districts

    # No district and no actionable status -> nothing structured to record.
    matched = (
        (bool(districts) or status in ("clear", "destroyed"))
        and not aftermath
        and not negated
        and not siren_only
        and not political_quote
    )
    if aftermath or negated or siren_only or political_quote:
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
        negated=negated,
        siren_only=siren_only,
        day_recap=day_recap,
        political_quote=political_quote,
        lost_signal=lost_signal,
    )

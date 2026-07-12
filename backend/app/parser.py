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

from .gazetteer import CITYWIDE_NAME_EN as _CITYWIDE_NAME_EN

# --- Target type keywords (checked in priority order) ---
# Ballistic / aeroballistic — checked FIRST: the most time-critical class
# (seconds of flight) and it must win over the generic "ракет" match in the
# same message ("балістична ракета" -> ballistic, not missile). Kept a DISTINCT
# type from cruise/generic "missile" because the two drive different behavior:
# a ballistic is sub-minute and un-spottable over a specific raion, so it's a
# CITY-WIDE, no-trajectory threat; a cruise missile flies a route spotters
# track district-to-district, so it draws a real vector. С-300/400 are launched
# in a ballistic (surface-to-surface) mode against cities — spotters call them
# балістика, so their designations belong here too.
_BALLISTIC = ("баліст", "іскандер", "кинджал", "с-400", "с400", "с-300", "с300",
              "аеробаліст")
# Cruise / guided-bomb / generic missile. Bare "ракет" is ambiguous (could be a
# ballistic) but defaults here — only an explicit ballistic marker above
# promotes a message to `ballistic`.
_MISSILE = ("ракет", "крилат", "калібр", "х-101", "х-59", "х-22",
            "каб", "авіабомб", "керован авіа")
_JET = ("реактивн", "швидкісн", "реактивного бпла")
_SHAHED = ("шахед", "shahed", "мопед", "герань", "герані", "дрон", "бпла",
           "безпілотник", "безпілотн")

# Grammatical-gender fallback: Ukrainian numeral agreement implies the target
# type even when the spotter never names it — "Один на водосховище" agrees
# with a masculine noun (шахед/дрон/БПЛА all masculine), so a bare "один"/
# "одне" with no other type keyword is almost certainly one of those, not a
# missile ("ракета" is feminine — "одна" would agree with THAT). Swept the
# real corpus: masculine forms appeared in 6/6 real target-count messages
# with zero counter-examples ("Один на водосховище", "Оболонь. Один
# залишився", "ще один на Славутич"...); feminine forms had ZERO real
# support for a missile reading — every "одна"/"одне" hit was casualty news
# ("Одна людина... загинула") where it agrees with "людина"/"тіло", not
# "ракета" — NOT adopted, real collision risk with a generic "одна ціль"
# phrasing we haven't seen yet but can't rule out. Reactive drones are
# excluded here since spotters always name "реактивний" explicitly (caught
# by _JET above) rather than omitting the type — a bare "один" is the
# unremarkable default (shahed/generic drone), not the jet variant.
_MASC_ONE_RE = re.compile(r"(?<![а-яіїєґ])(?:один|одне)(?![а-яіїєґ])", re.IGNORECASE)

# --- Status keywords ---
_CLEAR = ("відбій",)
# "Чекаємо/очікуємо (на) відбій" ANTICIPATES the all-clear — it is NOT one. The
# bare "відбій" stem would otherwise read these as a real clear and prematurely
# close every open track (and end the incident). Curated phrases, not the bare
# "чека"/"очіку" stems (those also appear in a genuine clear's "дякуємо за
# очікування").
_CLEAR_ANTICIPATION = ("чекаємо на відбій", "чекаємо відбій", "чекаєм на відбій",
                       "чекаєм відбій", "очікуємо відбій", "очікуємо на відбій",
                       "очікуєм відбій", "чекатимемо відбій", "очікуватимемо відбій",
                       "коли відбій", "коли вже відбій")
# "тривог" (the SIREN itself ended, e.g. "Відбій тривоги") is a strong signal
# the clear is general/unscoped, even if the same message also happens to
# name a target type. Used to gate clear_scope below — see that field's
# comment. Ballistic threats never carry a Kyiv district (see _MISSILE's
# "баліст" — sub-minute flight time, nobody spots them over a specific
# raion), so their own "Відбій балістики"-style stand-downs would otherwise
# be indistinguishable from a full all-clear and wrongly close every OTHER
# open track too (a real example: "тривога зберігається по цих БПЛА. По
# балістиці відбій." — БПЛА explicitly still active).
_UNSCOPED_CLEAR_WORD = "тривог"
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
# "ще N <noun>" ("ще 3 шахеди", "ще 2 цілі") — a stated group of ADDITIONAL
# targets, same shape as _COUNT_NOUN_RE below but prefixed with "ще" to catch
# the new-target reading. Noun-anchored (not bare "ще \d+") so a time
# reference like "ще 20хв" never matches — "хв" isn't a target noun.
_NEW_TARGET_COUNT_RE = re.compile(
    r"ще\s+\d+\s+(?:ракет|ціл|шахед|бпла|дрон|баліст)", re.IGNORECASE
)

# Explicit target-count shorthand spotters use: "2х", "їх вже 3х" (a number then
# х/x). The negative lookahead drops "20хв"=minutes and any number glued to a
# word. This is the stated size of a group flying together — one reply-chain
# track carries the whole group, so the count annotates the track (viz), it does
# NOT fabricate N separate tracks.
_COUNT_RE = re.compile(r"(\d+)\s*[хx](?![а-яіїєґa-z])", re.IGNORECASE)
# A number directly qualifying a target noun ("3 ракети", "2 цілі", "4 шахеди").
_COUNT_NOUN_RE = re.compile(r"(\d+)\s+(?:ракет|ціл|шахед|бпла|дрон|баліст)", re.IGNORECASE)

# Terse target/launch "pulse" words — a short callout of another target/launch
# with no location ("Ціль!", "Ще вихід", "Групова ціль", "3 ракети"). Too terse
# to localize alone, but DURING an active city-wide alert (ingest gates on that)
# it corroborates the alert and bumps the stated count — spotters calling the
# salvo in as it comes. "вихід" = a launch/exit callout in this feed.
_PULSE_WORD = ("ціль", "цілі", "вихід", "ракет", "баліст", "шахед", "бпла", "дрон")

# --- Aftermath / consequence vocabulary. A message describing the RESULT of a
# strike (casualties, damage, rescue) is NEWS about a place, not a live target
# to track — even if it names a district. These suppress a sighting. ---
_AFTERMATH = ("постраждал", "загинул", "поранен", "жертв", "уламк", "пошкодж",
              "зруйнов", "врятув", "рятувальник", "надзвичайник", "дснс",
              "багатоповерхів", "наслідк", "кмва", "госпіталіз", "медик",
              "евакуй", "загибл", "потерпіл",
              "пожеж",       # "пожежі на Трої" — fire footage is aftermath, not a sighting
              "відновленн")  # "виділить... на відновлення" — reconstruction-funding news

# --- Air-defence action vocabulary. "Відпрацювали установки по Дарницькому та
# Соломʼянському", "працює ППО" — a report that OUR air defence engaged over some
# districts. It's not an incoming target and not a trajectory: matching its two
# named districts would draw a bogus target-vector between them. Suppress it like
# aftermath (an impact keyword in the same message still wins — real strike). ---
_AD_ACTION = ("відпрацюв",   # відпрацювали/відпрацювала/відпрацьовує (установки/по цілі)
              "працює ппо", "ппо працює", "працює наша ппо", "сили ппо", "робота ппо")

# --- Impact / strike-location vocabulary. A LOCALIZED hit ("влучання по будівлі
# в Дніпровському районі", "пошкоджено будівлю у Святошинському") is a confirmed
# strike whose LOCATION is worth putting on the map — distinct from generic
# aftermath news (casualties/rescue/funding) that we suppress. Requires a
# district: without one ("є влучання десь") there is nothing to place. When both
# an impact verb AND aftermath words are present (a strike report that also
# mentions casualties), the impact reading WINS — the location is the useful
# signal. "пошкодж"/"зруйнов" also live in _AFTERMATH so a district-less "damaged
# a building" still suppresses; only WITH a district do they become an impact. ---
_IMPACT = ("влучанн", "приліт", "пошкодж", "зруйнов")

# Retrospective footage/report of a PAST strike ("На відео наслідки останньої
# атаки", "наслідки нічної атаки") — NOT a fresh hit to place on the live map. A
# genuine strike report ("влучання в Дніпровському районі") never frames itself
# as "останньої/минулої атаки" or "на відео". Blocks the impact reading so the
# message falls back to plain aftermath suppression (no live marker, no incident,
# no "attack" banner). ---
_RETROSPECTIVE = ("на відео", "останньої атаки", "минулої атаки", "нічної атаки",
                  "вчорашн", "минулої ночі")

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

# --- Conditional/speculative mood ("якщо піде...", "може піти...", "у разі
# оголошення тривоги...") — a hedge about a POSSIBLE future event, not a live
# confirmed sighting. Suppressed the same way as _NEGATION (an explicit
# clear/destroyed keyword elsewhere in the message still wins).
#
# Swept the full 871-message real corpus first (see gazetteer.py's "Щасливе"
# discipline — validate against real data before committing a heuristic):
# - Bare "якщо" is UNSAFE alone: it also occurs in a genuine live sighting
#   ("На Чернігівщині ще 2х реактивних, 5/8 хвилин до області, якщо по
#   прямій" — a distance qualifier, not a hedge about whether it's real).
#   Real conditional-attack-prediction messages instead pair "якщо" with a
#   consequence verb ("Якщо виліт БОЙОВИЙ, очікуємо на пуски ракет",
#   "Якщо балістична атака відбудеться, очікувати її слід…") — requiring
#   that co-occurrence is corpus-clean (checked all 18 real "якщо" hits).
# - Bare "у разі" is ALSO unsafe alone: it appears inside the unrelated idiom
#   "у/в жодному разі" ("under no circumstances") in the real corpus twice —
#   excluded via _CONDITIONAL_IDIOM_EXCLUDE.
# - "якщо піде"/"може піти" (the literal plan-specified phrases) had zero
#   hits in this corpus — kept anyway as forward cover for phrasing not yet
#   seen; specific enough (verb-anchored) to carry low collision risk.
_CONDITIONAL_PHRASES = ("якщо піде", "може піти")
_CONDITIONAL_IDIOM_EXCLUDE = ("жодному разі", "жодним разі")
_CONDITIONAL_CONSEQUENCE = ("очіку", "відбудеться", "відбуватимуться")


def _has_conditional_hedge(norm: str) -> bool:
    if any(p in norm for p in _CONDITIONAL_PHRASES):
        return True
    if "у разі" in norm and not any(x in norm for x in _CONDITIONAL_IDIOM_EXCLUDE):
        return True
    if "якщо" in norm and any(w in norm for w in _CONDITIONAL_CONSEQUENCE):
        return True
    return False


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

# --- City-wide threat: a strike aimed at the CITY as a whole, with no raion
# localization ("Ціль на місто!", "На Київ!", "Балістика на Київ"). During the
# sub-minute ballistic phase spotters warn the whole city before any raion is
# named, so these must produce a city-level alert instead of nothing. All three
# monitored channels are Kyiv-dedicated, so a directional callout IS about Kyiv.
# STRONG phrases are directional/imperative — the phrase itself is the threat
# signal ("На Київ!", "Увага місто!"), sufficient on their own. WEAK phrases
# ("по Києву") also appear in news/recaps ("новини по Києву"), so they need a
# threat-context word alongside. ---
_CITYWIDE_STRONG = ("на місто", "на київ", "на столиц", "увага місто", "увага, місто")
_CITYWIDE_WEAK = ("по місту", "по києву", "удар по києву", "по столиц")
_THREAT_CONTEXT = ("ціль", "цілі", "ракет", "баліст", "шахед", "бпла", "дрон",
                   "загроз", "удар", "приліт", "вибух", "кинджал", "іскандер",
                   "каб", "с-400", "с400", "с-300", "с300")

# --- Retrospective attack SUMMARY, not a live target ("Загалом по Києву пустили
# до 8 ракет", "Росія випустила близько 8 балістичних С-400 за останні 15
# хвилин"). These recap what ALREADY happened (aggregate count, past frame) —
# useful info, but NOT a live threat to raise a city alert for. Distinguished
# from a live callout ("3 ракети", "ціль на місто") by an aggregate/past marker.
# Curated word list, same shape as _AFTERMATH. "під час (нічної) атаки" is a
# retrospective FRAME — an after-the-fact report ("Під час нічної атаки на Київ
# запустили 6 балістичних… — ПС"), not a live callout. ---
_SUMMARY = ("загалом", "всього", "за останні", "випустил", "під час")

# --- Decoy / electronic-warfare vocabulary ("Ймовірно, імітація", "працює
# РЕБ", "хибна ціль") — a modifier on the attack (see app/attack.py::classify:
# decoy_suspected), NOT a replacement classification: a raid can be combined
# AND partially imitation. Curated list per the domain-model-v2 plan, same
# shape as _AFTERMATH/_NEGATION. "реб" is a 3-letter abbreviation that would
# otherwise collide with common words, so it goes in _WHOLE_WORD below (same
# treatment as "каб"). Behavioral inference ("every track vanished with no
# impacts" => decoy) is explicitly NOT done here — that's a hint at most,
# left to a human reading the incident, not a classifier signal. ---
_DECOY = ("імітаці", "реб", "обманк", "хибн", "фальшив")

# --- Hypersonic system names ("Кинджал", "Циркон", aeroballistic) — a flag on
# the attack (has_hypersonic), deliberately NOT a 6th target_type (that would
# spread into evals/icons/severity for one narrow rendering need). "кинджал"
# and "аеробаліст" already drive `target_type='ballistic'` via _BALLISTIC
# above; this list exists purely to ALSO raise the hypersonic flag alongside
# whatever target_type was already derived. ---
_HYPERSONIC = ("кинджал", "циркон", "аеробаліст")

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
    target_type: str  # 'shahed' | 'jet_drone' | 'missile' | 'ballistic' | 'unknown'
    status: str       # 'confirmed' | 'sighting' | 'unconfirmed' | 'destroyed' | 'clear'
    is_new_target: bool
    districts: list[DistrictHit]
    confidence: float
    target_count: int | None = None  # stated group size ("2х"), None if unstated
    raw_text: str = ""
    matched: bool = field(default=False)
    aftermath: bool = field(default=False)
    # A localized confirmed strike ("влучання ... в Дніпровському районі") — a
    # terminal marker to place on the map, NOT an active inbound target. Keeps
    # its district (unlike aftermath, which suppresses).
    impact: bool = field(default=False)
    negated: bool = field(default=False)
    siren_only: bool = field(default=False)
    day_recap: bool = field(default=False)
    political_quote: bool = field(default=False)
    lost_signal: bool = field(default=False)
    # A city-level threat with no raion of its own ("Ціль на місто!") — ingest
    # raises a single city-wide alert instead of a per-district track.
    citywide: bool = field(default=False)
    # A retrospective recap of the attack ("загалом ... 8 ракет"), not a live
    # target — info only, must not raise a city alert or track.
    summary: bool = field(default=False)
    # A terse target/launch callout with no place ("Ціль!", "Ще вихід") — only
    # acted on (as corroboration) when a city-wide alert is already open.
    target_pulse: bool = field(default=False)
    # None = a genuine full clear ("Відбій тривоги та всіх загроз") — closes
    # every open track. A target type = an all-clear scoped to just THAT
    # type ("Відбій балістичної загрози з Криму") — must not close unrelated
    # open tracks (e.g. an active shahed). Only set when status == "clear".
    clear_scope: str | None = field(default=None)
    # Decoy/EW vocabulary present ("імітація", "РЕБ", "хибна ціль") — a
    # modifier accumulated onto the incident (see app/attack.py), not a
    # replacement classification.
    decoy: bool = field(default=False)
    # A hypersonic system named (Кинджал/Циркон/aeroballistic) — a flag on
    # the incident, not a 6th target_type.
    hypersonic: bool = field(default=False)


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
# "каб" inside "кабель"/"кабіна", "реб" inside "теребити"/"ребро"). Match
# those as whole words; match everything else at a word start so inflected
# suffixes still hit (ракет→ракети).
_WHOLE_WORD = {"каб", "реб"}


def _kw_regex(words) -> re.Pattern:
    parts = []
    for w in words:
        esc = re.escape(w)
        if w in _WHOLE_WORD:
            parts.append(r"(?<![а-яіїєґ])" + esc + r"(?![а-яіїєґ])")
        else:
            parts.append(r"(?<![а-яіїєґ])" + esc)
    return re.compile("|".join(parts))


_BALLISTIC_RE = _kw_regex(_BALLISTIC)
_MISSILE_RE = _kw_regex(_MISSILE)
_JET_RE = _kw_regex(_JET)
_SHAHED_RE = _kw_regex(_SHAHED)
_DECOY_RE = _kw_regex(_DECOY)
_HYPERSONIC_RE = _kw_regex(_HYPERSONIC)


def _target_type(norm: str) -> str:
    if _BALLISTIC_RE.search(norm):
        return "ballistic"
    if _MISSILE_RE.search(norm):
        return "missile"
    if _JET_RE.search(norm):
        return "jet_drone"
    if _SHAHED_RE.search(norm):
        return "shahed"
    if _MASC_ONE_RE.search(norm):
        return "shahed"
    return "unknown"


def _target_count(norm: str) -> int | None:
    """The largest sane group count stated in the text ("2х"->2, "3 ракети"->3)."""
    nums = [int(m.group(1)) for m in _COUNT_RE.finditer(norm)]
    nums += [int(m.group(1)) for m in _COUNT_NOUN_RE.finditer(norm)]
    nums = [n for n in nums if 1 <= n <= 50]  # ignore junk like "100х"/years
    return max(nums) if nums else None


def _status(text: str, norm: str) -> tuple[str, float]:
    """Return (status, base_confidence)."""
    if any(k in norm for k in _CLEAR) and not any(a in norm for a in _CLEAR_ANTICIPATION):
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
    is_new = any(k in norm for k in _NEW_TARGET) or bool(_NEW_TARGET_COUNT_RE.search(norm))
    target_count = _target_count(norm)
    districts = matcher.find(norm)
    # Unconditional modifier flags — computed regardless of matched/
    # suppression status, since a decoy/hypersonic mention is worth
    # accumulating onto the incident even on an otherwise-terse message.
    decoy = bool(_DECOY_RE.search(norm))
    hypersonic = bool(_HYPERSONIC_RE.search(norm))

    # A clear/відбій is scoped to just the named type when the message states a
    # missile-family type ("Відбій балістичної загрози" -> ballistic; a cruise
    # "відбій ракетної небезпеки" -> missile) and doesn't ALSO say the siren
    # itself ended. A ballistic stand-down must not close active cruise/shahed
    # tracks, and vice versa. See _UNSCOPED_CLEAR_WORD's comment for the real
    # example this guards.
    clear_scope = (
        target_type
        if status == "clear" and target_type in ("ballistic", "missile")
        and _UNSCOPED_CLEAR_WORD not in norm
        else None
    )

    # Impact / localized strike ("влучання по будівлі в Дніпровському районі"):
    # a confirmed hit whose LOCATION we map as a terminal marker. Needs a
    # district; a destroyed/clear keyword is a stronger, more specific status
    # and wins over an impact reading.
    impact = (
        bool(districts)
        and any(k in norm for k in _IMPACT)
        and status not in ("clear", "destroyed")
        and not any(k in norm for k in _RETROSPECTIVE)
    )

    # Aftermath/consequence news ("постраждала багатоповерхівка", "врятували
    # дитину") mentions a district but is NOT a live target — suppress it, unless
    # it's an all-clear (which legitimately closes tracks) or a localized impact
    # (which we keep and map — the strike location is the useful signal).
    aftermath = any(k in norm for k in _AFTERMATH) and status != "clear" and not impact

    # Air-defence engaged over some districts ("Відпрацювали установки по X та Y")
    # — defensive action, not an incoming target. Suppressed like aftermath so it
    # never becomes a track (and never a bogus X→Y vector); a real strike keyword
    # in the same message still wins via the impact carve-out.
    ad_action = any(k in norm for k in _AD_ACTION) and status not in ("clear", "destroyed") and not impact

    # Explicit denial ("Не йде на Оболонь") mentions a district but says the
    # target is NOT there — suppress it, same carve-out as aftermath: an
    # explicit clear/destroyed keyword elsewhere in the message still wins (its
    # own keyword signal is stronger evidence than a coincidental negation word).
    # A conditional/speculative hedge ("якщо піде…", "у разі оголошення
    # тривоги…") gets the same treatment — see _has_conditional_hedge.
    negated = (
        any(k in norm for k in _NEGATION) or _has_conditional_hedge(norm)
    ) and status not in ("clear", "destroyed")

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
    # comment for why a district-bearing message must never match this. Same
    # carve-out as negated/siren_only: an explicit clear/destroyed keyword in
    # the SAME message ("Мінуснули, Дорозвідка" — one target confirmed
    # destroyed, "дорозвідка" here is just a follow-up status note) is the
    # stronger, more specific signal and must win — otherwise it would
    # incorrectly close EVERY open track as "lost" instead of just the one
    # destroyed target.
    lost_signal = _LOST_WORD in norm and not districts and status not in ("clear", "destroyed")

    # Retrospective summary of the whole attack (aggregate/past-frame count) —
    # info, not a live target. Blocks the city-alert / track it would otherwise
    # raise. Only meaningful on a threat-flavoured message.
    summary = any(k in norm for k in _SUMMARY) and (
        target_type != "unknown" or any(w in norm for w in _THREAT_CONTEXT)
    )

    # City-wide threat: a city-level phrase with NO raion of its own — a strong
    # directional phrase on its own, or a weak one plus a threat-context word.
    # Only when nothing else localizes or supersedes it: a real district, an
    # all-clear/destroyed, aftermath/negation/siren/quote, or a retrospective
    # summary all take precedence. ingest.py turns this into ONE city-level alert.
    citywide = (
        not districts
        and status not in ("clear", "destroyed")
        and not (aftermath or negated or siren_only or political_quote
                 or lost_signal or summary or ad_action)
        and (
            any(p in norm for p in _CITYWIDE_STRONG)
            or (any(p in norm for p in _CITYWIDE_WEAK)
                and any(w in norm for w in _THREAT_CONTEXT))
        )
    )

    # Terse target/launch pulse: a very short callout ("Ціль!", "Ще вихід",
    # "Групова ціль", "3 ракети") naming a target/launch but no place. The
    # length cap keeps out longer sentences (which are usually status prose,
    # e.g. "Наразі повторні цілі відсутні…"), and all the suppressor flags are
    # excluded so a negated/recap line never pulses. ingest.py only ACTS on this
    # when a city-wide alert is already open — alone it's too terse to localize.
    target_pulse = (
        not districts
        and not citywide
        and status not in ("clear", "destroyed")
        and not (aftermath or negated or siren_only or political_quote
                 or lost_signal or summary or ad_action)
        and len(norm.split()) <= 3
        and any(any(p in w for p in _PULSE_WORD) for w in norm.split())
    )

    # No district and no actionable status -> nothing structured to record.
    matched = (
        (bool(districts) or citywide or status in ("clear", "destroyed"))
        and not aftermath
        and not negated
        and not siren_only
        and not political_quote
        and not ad_action
    )
    if aftermath or negated or siren_only or political_quote or ad_action:
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
        impact=impact,
        negated=negated,
        siren_only=siren_only,
        day_recap=day_recap,
        political_quote=political_quote,
        lost_signal=lost_signal,
        clear_scope=clear_scope,
        citywide=citywide,
        summary=summary,
        target_pulse=target_pulse,
        decoy=decoy,
        hypersonic=hypersonic,
    )

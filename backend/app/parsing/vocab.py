"""Curated Ukrainian keyword/phrase vocabulary and regex literals for the rule
parser (see `rules.py`). Pure data — no matching/decision logic here.

Every list is narrow on purpose. A word marked REJECTED, or a note that a list is
gated, is a recorded corpus finding — widening it there has broken the live map
before. `git log -p` on this file carries the case behind each one; GAZETTEER.md
covers the whole-word aliases at the bottom.
"""

from __future__ import annotations

import re

from ..regions import REGION_SPECS

# --- Target type keywords, checked in the order they are declared ---

# First, so it beats the generic "ракет" in the same message. С-300/400 fly
# surface-to-surface at cities. "КН-23" is ballistic but NOT _HYPERSONIC.
_BALLISTIC = ("баліст", "іскандер", "кинджал", "кн-23", "кн23", "с-400", "с400",
              "с-300", "с300", "аеробаліст", "циркон", "гіперзвук")
# Split from the generic "ракет" by how SPECIFIC the identification is: only a
# named weapon may correct a channel's ballistic type context
# (ingest/context.py::_note_and_inherit_type).
_MISSILE_NAMED = ("крилат", "калібр", "х-101", "х-59", "х-22")
# A glide bomb is not a missile: released across the border, lands near it.
# "каб" is whole-word (rules._WHOLE_WORD) — it heads "кабінет"/"Кабмін" — so the
# oblique forms are listed explicitly rather than the stem relaxed.
# 💣 is sumyregion's own marker for the same weapon.
_KAB = ("каб", "каби", "кабів", "кабам", "кабами", "авіабомб", "керован авіа", "💣")
_MISSILE_WEAPON = ("ракет", *_MISSILE_NAMED)
# The CARRIER, not the weapon — spotters name it hours before a launch, so it
# must never become the channel's live target type. "тушок" has a fleeting vowel,
# so the "тушк" stem does not reach it.
_MISSILE_CARRIER = ("стратегічн авіац", "стратегічної авіа", "тушк", "тушок",
                    "ту-95", "ту95", "ту-160", "ту160", "бомбардувальник")
_MISSILE = _MISSILE_WEAPON + _MISSILE_CARRIER
# Checked BEFORE _MISSILE: the feed calls Бандероль a "ракета" and a "баражуючий
# боєприпас", and the generic stem would win the chain. MODEL names only.
_JET_MODEL = ("бандерол", "молні")
# Bare "реактив" — the noun form is used too ("3 реактива повз Славутич").
# "рбпла" = реактивний БПЛА; keywords anchor on a word START, so _UAV's "бпла"
# cannot see it behind the "р".
_JET = ("реактив", "швидкісн", "рбпла")
# The GENERIC drone bucket, feeding target_type == "shahed" — a wire value frozen
# in the DB, the OpenAPI schema, the LLM enum rail and the eval rows, so that
# string stays however the list grows.
# "шах" is the Сумщина/RDS short form, whole-word (rules._WHOLE_WORD) for the
# same reason "каб" is: as a stem it heads "шахрай"/"шахта"/"шахтар".
_UAV = ("шахед", "shahed", "мопед", "герань", "герані", "дрон", "бпла",
           "безпілотник", "безпілотн", "баражуюч", "баражаюч",
           "ланцет", "італмас", "гербер",
           "шах", "шаха", "шаху", "шахи", "шахів", "шахам", "шахами")
# Its own TargetType rather than a drone: ~20 km of range against a Shahed's
# 1000+, rooftop height, stale within minutes. "оптоволок" is the control spool,
# only ever written about an FPV on this feed.
_FPV = ("fpv", "фпв", "оптоволок")
# A bare masculine numeral implies a drone — шахед/дрон/БПЛА are masculine,
# "ракета" is feminine. Feminine "одна" REJECTED: every real hit was casualty
# news agreeing with "людина"/"тіло". Jets always say "реактивний" (_JET).
_MASC_ONE_RE = re.compile(r"(?<![а-яіїєґ])(?:один|одне)(?![а-яіїєґ])", re.IGNORECASE)

# --- Status keywords ---
_CLEAR = ("відбій",)
# "Чекаємо відбій" ANTICIPATES the all-clear; the bare stem would read it as one
# and close every open track. Curated phrases, not the "чека"/"очіку" stems.
_CLEAR_ANTICIPATION = ("чекаємо на відбій", "чекаємо відбій", "чекаєм на відбій",
                       "чекаєм відбій", "очікуємо відбій", "очікуємо на відбій",
                       "очікуєм відбій", "чекатимемо відбій", "очікуватимемо відбій",
                       "очікуватимемо на відбій", "очікується відбій",
                       "очікувати на відбій", "очікувати відбій", "очікувати відбою",
                       "чекати відбій", "чекати на відбій", "чекати відбою",
                       "чекаємо відбою", "чекатимемо відбою", "очікуємо відбою",
                       "очікуватимемо відбою", "очікується відбою",
                       "коли відбій", "коли вже відбій",
                       "скоро відбій", "надія на відбій")
# The SIREN ended => the clear is unscoped even when a type is also named, so
# "По балістиці відбій" cannot close unrelated tracks.
_UNSCOPED_CLEAR_WORD = "тривог"
# "мінус" = spotter shorthand for a downed target.
_DESTROYED = ("збил", "збито", "знищ", "нейтраліз", "уражен", "ліквідов", "впав",
              "мінус")
_UNCONFIRMED = ("уточнюється", "непідтвердж", "не підтвердж", "попередньо", "можливо")
_CONFIRMED = ("підтвердж", "🔴")

# Small counts are written as WORDS as often as digits, and the rules below were
# digit-only, so every one of them read as a single target.
# Apostrophe-less spellings only (`normalize` strips apostrophes). Stops at ten:
# past that spotters use digits.
_NUM_WORDS: dict[str, int] = {
    "два": 2, "дві": 2, "двоє": 2, "двох": 2,
    "три": 3, "троє": 3, "трьох": 3,
    "чотири": 4, "четверо": 4, "чотирьох": 4,
    "пять": 5, "пятеро": 5, "пяти": 5,
    "шість": 6, "шестеро": 6, "шести": 6,
    "сім": 7, "семеро": 7, "семи": 7,
    "вісім": 8, "восьмеро": 8, "восьми": 8,
    "девять": 9, "девятеро": 9, "девяти": 9,
    "десять": 10, "десятеро": 10, "десяти": 10,
    # Listed on purpose: it ENDS in "два"/"дві", so without its own entry it
    # would be counted anyway, by the accident of a suffix match.
    "обидва": 2, "обидві": 2, "обох": 2,
}
# Longest-first, so "двоє" can't be shadowed by "два" (and "обидва" not by "два").
_NUM_WORD_ALT = "|".join(sorted(map(re.escape, _NUM_WORDS), key=len, reverse=True))
# The word branch carries its own word-START guard (callers anchor only the end,
# so nothing else stops a numeral matching the TAIL of a longer word). Inside the
# branch, so the digit form keeps matching exactly what it did.
_NUM = rf"(?:\d+|(?<![а-яіїєґ])(?:{_NUM_WORD_ALT}))"
_NUM_SHORT = rf"(?:\d{{1,2}}|(?<![а-яіїєґ])(?:{_NUM_WORD_ALT}))"


def count_value(token: str) -> int | None:
    """An int from either a digit run or a numeral word, else None."""
    return int(token) if token.isdigit() else _NUM_WORDS.get(token)


# --- New-target markers (start a fresh track) ---
_NEW_TARGET = ("новий", "нова ціль", "ще один", "ще одна", "інша ціль",
               "друга ціль", "додатков", "нові цілі")
# Noun-anchored, not bare "ще N", so a time reference ("ще 20хв") never matches.
# Type ADJECTIVES belong here for the same reason as in _COUNT_NOUN_RE: the noun
# a spotter picks after one is unpredictable.
_NEW_TARGET_COUNT_RE = re.compile(
    rf"ще\s+{_NUM}\s+(?:ракет|ціл|шахед|бпла|дрон|баліст|реактивн|крилат|циркон|калібр)",
    re.IGNORECASE,
)

# A number then х/x ("2х"). The lookahead drops "20хв" and numbers glued to
# words. This is the size of ONE group — it never fabricates N tracks.
_COUNT_RE = re.compile(r"(\d+)\s*[хx](?![а-яіїєґa-z])", re.IGNORECASE)
# A number qualifying a target noun ("3 ракети") — or a type ADJECTIVE, since
# spotters put the number in front of those too ("10 реактивних Шахедів").
_COUNT_NOUN_RE = re.compile(
    rf"({_NUM})\s+(?:ракет|ціл|шахед|бпла|дрон|баліст|реактивн|крилат|калібр|циркон)",
    re.IGNORECASE,
)
# A bare number heading for a place ("3 на Славутич"). Deliberately only HALF the
# rule: the caller additionally requires a gazetteer-matched place to start where
# this ends (rules.py::_target_count), because a bare digit before a preposition
# alone would read "Ту-22м3 на Київщину" as 3 targets. The lookbehind rejects a
# digit glued to a word or number and time-ish forms.
_COUNT_TO_PLACE_RE = re.compile(
    rf"(?<![0-9а-яіїєґa-z:.,])({_NUM_SHORT})\s+"
    r"(?:на|над|до|біля|курсом\s+на|у\s+напрямку(?:\s+на)?)\s+",
    re.IGNORECASE,
)
# A number that is DOING something ("Знову 3 долітають до Броварів") — the verb
# is the anchor, so a place may sit several words away or be absent.
# PRESENT TENSE ONLY, and that is the guard: the past tense is the voice of
# recaps, whose numbers are night-long salvo totals, and stamping one on a
# district track had the journal reporting hundreds of phantom targets.
_COUNT_MOVING_RE = re.compile(
    rf"(?<![0-9а-яіїєґa-z:.,])({_NUM_SHORT})\s+"
    r"(?:долітаю|долітає|летят|летить|йдут|ідут|іде\b|рухаю|сунут|заходят|прямую|проходят)",
    re.IGNORECASE,
)
# A count written NEXT TO the place with nothing between them ("Замглай два",
# "Бровари 6 штук") — how the northern channel counts almost everything.
# Place-anchored half-rules like _COUNT_TO_PLACE_RE: the caller applies them to
# the text right after / before a gazetteer match, and the match's real end is
# what tells "Район ТЕЦ два" (a count) from "ТЕЦ-5" (part of the name).
# Guards: at least one separator, not a clock or decimal, not a unit ("Ніжин 5 хв"
# is a warning time). Ordinals need no guard — none is a _NUM_WORDS entry.
_NOT_A_COUNT_TAIL = r"(?![а-яіїєґ0-9])(?![.:]\d)(?!\s*(?:хв|год|км|сек)[а-яіїєґ]*)"
_COUNT_AFTER_PLACE_RE = re.compile(
    rf"^[\s,.•]{{1,3}}({_NUM_SHORT}){_NOT_A_COUNT_TAIL}", re.IGNORECASE)
_COUNT_BEFORE_PLACE_RE = re.compile(
    rf"(?<![-:0-9а-яіїєґa-z])({_NUM_SHORT}){_NOT_A_COUNT_TAIL}[\s,.•]{{1,3}}$", re.IGNORECASE)

# Terse target/launch "pulse" with no location ("Ціль!", "Ще вихід"). Too terse
# to localize alone; only acted on during an open city-wide alert.
_PULSE_WORD = ("ціль", "цілі", "вихід", "ракет", "баліст", "шахед", "бпла", "дрон",
               "циркон",
               "цілей",   # genitive — "ціль"/"цілі" don't substring-match it
               "пуск",    # "Ще пуски!"
               "пада",    # "Падають!" — live incoming
               "летить", "летять",
               # Type adjectives spotters use alone, noun implicit.
               "реактивн", "крилат", "калібр")

# A pulse corroborates the KYIV city alert, so it must not name a place we can't
# recognize: a word right after one of these prepositions is in TARGET position,
# and if the gazetteer missed it the message is about somewhere else.
# FROM-position prepositions (з/зі/від) are deliberately absent — an origin is
# legitimately ours and already pulses ("Балістика з Курщини").
_PULSE_TARGET_PREP = ("на", "над", "до", "біля", "під", "по", "у", "в")
# Kyiv itself is not an unknown place. Target vocabulary is allowed by the caller.
_PULSE_PREP_KNOWN = ("київ", "києв", "столиц", "міст")

# Raions put on notice for a target that has NOT reached them — one message
# routinely carries both claims ("Пухівка/Зазимʼя 🔴 та готовність Бровари").
# "Увага"/"уважно" deliberately do NOT belong here: they head plain callouts.
_READINESS_RE = re.compile(r"(?<![а-яіїєґ])(?:готовн|поготов|приготуй)[а-яіїєґ]*")
_SENTENCE_END_RE = re.compile(r"[.!?\n]")
# A gazetteer hit's own word, to find where it ends (DistrictHit carries only its
# start offset), and the connectors that make several hits ONE coordinated list.
_TOPONYM_WORD_RE = re.compile(r"[а-яіїєґ'’ʼ\-]+")
_LIST_JOIN_RE = re.compile(r"^[\s/,]*(?:та|і|й)?[\s/,]*$")

# Mark a multi-district message as ONE target on a route rather than an
# enumeration of simultaneous targets — the latter recreates the zigzag
# mega-track.
_MOVEMENT_CUE = ("курс", "у бік", "в бік", "через", "прямує", "рухаєт", "повз",
                 "напрям", "заходить", "захід у", "летить на")
# A district in a prepositional phrase is a located frame, not an enumeration item.
_PREPOSITION_BEFORE_DISTRICT = ("на", "у", "в", "до", "з", "зі", "із", "над",
                                "біля", "під", "по")

# Between two named places: a path FROM the earlier one TO the later ("Мамекине
# на Смяч"). Deliberately excludes the FROM-markers "з"/"від" — "На Смяч з
# Мамекиного" puts the destination first, and drawing text order would reverse
# the arrow. That shape does not occur in the corpus, so it is left unhandled
# rather than guessed at.
_PATH_CONNECTIVE = ("на", "до", "через", "повз")
# Only these may stand between the connective and the destination; anything else
# means the connective governs something other than the place.
_PATH_FILLER = ("район", "районі", "району", "районом", "рн", "р-н",
                "лівий", "правий", "бік", "боку", "сторону", "межу", "межі")
# A gap carrying its own count is a DISTRIBUTION of separate targets, not one
# path ("6 БпЛА на Вишгород, 2 на Згурівку").
_PATH_COUNT_BREAK = ("ще один", "ще одна", "ще два", "ще дві", "другий", "друга",
                     "друге", "третій", "третя", "інший", "інша", "група")

# The RESULT of a strike is news about a place, not a live target, even when it
# names a district.
_AFTERMATH = ("постраждал", "загинул", "поранен", "жертв", "уламк", "пошкодж",
              "зруйнов", "врятув", "рятувальник", "надзвичайник", "дснс",
              "багатоповерхів", "наслідк", "кмва", "госпіталіз", "медик",
              "евакуй", "загибл", "потерпіл",
              "пожеж",
              # Post-strike fire. NOT the bare stem "горіл": it sits inside the
              # village Погорільці.
              "горить", "горять", "вигорі", "згорі",
              # Full forms, NOT the stem "пала" — "ракета впала" contains it.
              "палає", "палають", "палала", "палало",
              "відновленн",
              # Qualified forms only: the bare "дим" sits inside Димер, Димерка
              # and "видимість".
              "густий дим", "сильний дим", "позачиняти вікна", "закрийте вікна",
              # The channel explaining what a sound WAS — commentary about a
              # place, never a target over it.
              "може чути", "можете чути")

# Aftermath CATEGORIES. Read only by domain/aftermath.py: `_AFTERMATH` above
# decides whether a message is suppressed and must keep deciding exactly what it
# decides today, these four decide what an already-suppressed message is ABOUT.
# Folding them together was measured to suppress messages that currently keep a
# live raion.
# fire vs damage is "is it still happening"; the same question puts rescue above
# fire in the severity order (domain/aftermath).
_CAT_CASUALTIES = ("загинул", "загибл", "поранен", "жертв", "потерпіл", "госпіталіз",
                   "постраждал", "тіло", "тіла", "під завалами", "з-під завалів")
_CAT_RESCUE = ("рятувальник", "дснс", "надзвичайник", "врятув", "евакуй", "деблокув",
               "пошуково-рятувальн", "тривають пошуки", "заблокован", "піротехнік")
_CAT_FIRE = ("пожеж", "горить", "горять", "загорянн", "палає", "палають", "палала",
             "палало", "загоранн")
_CAT_DAMAGE = ("пошкодж", "зруйнов", "понівечен", "вигорі", "згорі", "уламк", "завал",
               "відновленн", "руйнув")

# "постраждал" is the one word in _CAT_CASUALTIES that a BUILDING can do, so it
# is anchored to the following noun rather than dropped from the list (which
# would cost "двоє людей постраждали" its only casualties word).
_STRUCTURE_HARM_RE = re.compile(
    r"постраждал\w*\s+(?:багатоповерхів|будин|будівл|будов|склад|авто|гуртожит|поверх)"
)

# Not an aftermath at all, though it reads like one: an ANNOUNCED controlled
# demolition, and the rescue service doing its ordinary peacetime job (an oil
# spill pinned onto Почайна). Blocks the aftermath RECORD only — the message is
# suppressed either way, which is why this is not part of `_AFTERMATH`.
_NOT_AN_AFTERMATH = ("знищення вибухонебезпечн", "планове знищення", "планові тренуванн",
                     "загрози не становлять", "не становить загрози",
                     "забруднення", "нафтопродукт")

# The aftermath record needs one of these or a live incident in the region (see
# domain/aftermath.py): "Поділ. Горять автомобілі" names no attack and could as
# well be a car fire in July.
# "вибух" carries a veto — "вибухонебезпечних предметів" is the announced
# demolition above, the exact phrase this gate must not wave through.
_STRIKE_WORD = ("атак", "удар", "обстріл", "влучанн", "приліт", "вибух",
                "бпла", "ракет", "шахед", "дрон")
_STRIKE_WORD_VETO = ("вибухонебезпечн",)

# Our air defence engaged — not an incoming target, and matching its two
# districts would draw a bogus vector between them.
_AD_ACTION = ("відпрацюв",
              "працює ппо", "ппо працює", "працює наша ппо", "сили ппо", "робота ппо")

# Civic notices the channels reprint: they name streets/neighbourhoods the
# gazetteer matches but are city news. Bare "маршрут"/"рух"/"транспорт" are
# deliberately absent — a real target "змінила маршрут руху"; only transport-mode
# words and multiword traffic phrases are safe.
_CIVIC_NOTICE = ("тролейбус", "трамвай", "маршрутк", "фунікулер", "автобус",
                 "громадського транспорт", "громадський транспорт",
                 "дорожнього руху", "рух транспорт", "руху транспорт",
                 "організації руху", "обмежать рух", "обмежуватимуть рух",
                 "перекрито рух", "перекрито середню",
                 # Street closures for a visiting delegation — same register,
                 # and they name "Центр" the same way.
                 "перекриють", "обмеження запровадж", "охоронних заход",
                 # Scheduled utility works naming a neighbourhood.
                 "водопостачанн", "водогін", "ремонтних робіт", "ремонтні роботи",
                 "планові роботи", "зниження тиску", "профілактичн",
                 # City-services news naming beaches, lakes, neighbourhoods.
                 "пляж", "водойм", "відповідає нормам", "якість води",
                 # A blackout report names the half of the city it happened in.
                 "зникло світло")

# єППО = the crowd-sensor app. Spotters relay its marks while dismissing them, so
# suppress only when a mention is PAIRED with a dismissal cue — "єППО показує
# ціль на Троєщині, підтверджую" must survive. _EPPO_WORD covers the Cyrillic-є
# spelling and the common Cyrillic-е typo.
_EPPO_WORD = ("єппо", "еппо")
_EPPO_DISMISS = ("не видно", "не бачим", "не фіксу", "не спостеріга", "дорозвідк",
                 "хибн", "локаційно чист")

# A LOCALIZED hit worth mapping, as opposed to generic aftermath news. Needs a
# district. When impact verbs and aftermath words co-occur, impact WINS — the
# location is the useful signal; "пошкодж"/"зруйнов" are in _AFTERMATH too, so
# without a district they still suppress.
_IMPACT = ("влучанн", "влучил", "приліт", "пошкодж", "зруйнов")

# Retrospective footage/report of a PAST strike. Blocks the impact reading only
# (the message falls back to aftermath suppression); it does NOT block a citywide
# reading — see _SUMMARY for the phrases that must.
_RETROSPECTIVE = ("на відео", "останньої атаки", "минулої атаки", "нічної атаки",
                  "вчорашн", "минулої ночі")

# Grid outages say "пошкодж" next to districts, which `_impact` otherwise reads
# as a confirmed hit. Blocks impact unless an unambiguous strike word
# (влучанн/приліт) is present too. Grid-specific stems, not bare "світл", so a
# building strike mentioning lights survives.
_POWER_OUTAGE = ("електропостачанн", "електроенерг", "електромереж", "енергетик",
                 "енергооб", "знеструмл", "підстанці", "обленерго", "дтек",
                 "аварійне пошкодж", "немає світл", "нема світл", "без світл",
                 "зникло світл", "відключенн світл")

# Explicit denial. Curated phrases, not bare "не" — that would swallow "не
# підтверджено" (a different status). LIMITATION: message-scoped, so a message
# that denies one target and reports another live one is dropped whole.
_NEGATION = ("не йде", "не летить", "не рухається", "не курсом", "не в бік",
             "не фіксується", "не спостерігається", "не зафіксовано",
             "без загроз", "поза загрозою")

# Conditional/speculative hedge — a possible future event, not a sighting.
# Bare "якщо" is UNSAFE (a live sighting uses it as a distance qualifier, "якщо
# по прямій"), so it needs a consequence verb alongside. Bare "у разі" is unsafe
# too — the idiom "у жодному разі" — hence the exclude list.
# "може піти" REMOVED: it hedges where a REAL target goes NEXT, not whether it
# exists, and it was suppressing live callouts whole.
_CONDITIONAL_PHRASES = ("якщо піде",)
_CONDITIONAL_IDIOM_EXCLUDE = ("жодному разі", "жодним разі")
_CONDITIONAL_CONSEQUENCE = ("очіку", "відбудеться", "відбуватимуться")

# Preparatory/forecast advisory — a planned future strike, not one in flight.
# "готу" is safe as a bare stem only because rules gates it on a weapon word
# (_THREAT_CONTEXT). "план" is NOT safe even gated ("Кияни, плануйте день…"), so
# only 3rd-person "планує"/"планують" — always the enemy. "може застосув" stays a
# two-word phrase; the bare stem collides with "загроза застосування балістики".
_FORECAST_VERB = ("готу", "планує", "планують", "може застосув", "можуть застосув")

# Night/evening forecast — a heads-up about a coming night. The register is
# nominal, so the anchor is the timeframe phrase, gated on a weapon word.
# "вночі" REJECTED — too broad, collides with aftermath recaps.
_FORECAST_TIMEFRAME = ("на сьогоднішню ніч", "на цю ніч", "цієї ночі", "на ніч",
                       "протягом ночі", "на вечір", "найближчими ноч")

# "можуть бути" as a bare hedge is UNSAFE: a real strike report uses it for an
# unrelated clause ("під завалами можуть бути люди") and a bare match would wipe
# that correct impact marker. Anchored to a following explosion/strike noun.
_HEDGE_MODAL_RE = re.compile(r"(?:можуть бути|може бути)\s+(вибух|обстріл|удар|приліт|пуск)")

# Advisory / relayed-opinion preview of which raions MIGHT be hit — second-hand
# or forecast, not first-hand, and each listed real raions and raised live dots.
# These phrases are self-sufficient (corpus: they appear ONLY in this class); the
# nominal "підвищена загроза" and "ворога цікавлять" markers need a weapon word
# and live in rules._has_conditional_hedge instead.
_ADVISORY_RELAY = ("пишуть що", "пишуть, що", "інших джерелах", "є попередження про",
                   "за даними", "до застосування", "підвезенн", "маю інформац")

# Recon-analysis prose — an intelligence write-up, not a callout. It names raions
# and its weapon words seeded a false type via inheritance. Gated on a weapon
# word; every marker is 0-hit in the real spotter corpus.
_RECON_ANALYSIS = ("у фокусі противник", "розвідувальних заход", "опрацюванн",
                   "приділяє")

# Siren echo ("Тривога у Вишгородському районі"): a place but no target type at
# all. A real sighting here always states a type.
_SIREN_WORD = "тривог"
# The raion need not be a GAZETTEER entry: the oblast monitors post one line per
# raion, and the raion adjective often has no stem of its own ("прилуцьк" is not
# "прилук"), which decided whether the identical template was suppressed or sent
# to the LLM. Requires _SIREN_WORD alongside, which keeps a live "ціль на
# Броварський район" out.
_RAION_PHRASE_RE = re.compile(r"\w+[сц]ьк(?:ому|ий|ого|ім)\s+район")

# Day recap ("Знову Деснянський район під атакою сьогодні"). "сьогодні" also
# appears in real sightings, so this only lowers confidence and KEEPS the
# district — safer than suppressing.
_DAY_RECAP_WORD = "сьогодн"

# Buzz-slang: "бджілки"/"бджоли" = OUR drones over enemy territory, so the
# message is reassurance chatter. It must not set or consume the per-channel type
# context (ingest._note_and_inherit_type) — one carrying "реактивні" typed the
# channel and a citywide ballistic callout inherited it seconds later.
_BUZZ_CHATTER = ("бджілк", "бджол")

# Explainer posts — a channel telling readers what a weapon IS, not that one is
# flying. Same treatment and reason as buzz-slang: with no district the model
# name is the ONLY thing the message contributes.
# "що таке" is the whole marker and deliberately nothing broader: "нагадування"
# is how this channel opens a REAL warning, and "пояснення" sits in genuine
# threat commentary.
_EXPLAINER = ("що таке", "шо таке")

# Ground-war / disinformation news. These name border villages the Сумщина
# gazetteer matches, so each raised phantom air tracks. The class is about the
# GROUND front or about what russian channels claim, never about the sky.
_GROUND_WAR = ("захопленн", "фейк", "пропагандист", "дезінформац", "іпсо",
               "не відповідає дійсності", "прориву оборони", "критично ставит")

# Personal prose from the channel admin — reminiscence, a birthday thank-you.
# Long-form, names places in passing, and nothing else reads it as anything but a
# sighting. The stem, NOT "памятаю, як": normalize() keeps the comma, so the
# phrase form would miss a variant written without one.
_PERSONAL_POST = ("памятаю",)

# Political/official quote naming a place — a news repost, about WHO is speaking.
# Marker: dash + named official. A curated name list is proportionate; a generic
# "dash + capitalized surname" regex would be far riskier.
_QUOTE_ATTRIBUTION_RE = re.compile(
    r"[—-]\s*(президент\w*|зеленськ\w*|сирськ\w*|кличк\w*|ігнат\w*|умєров\w*|"
    r"буданов\w*|малюк\w*|генштаб\w*)",
    re.IGNORECASE,
)

# Second-hand reportage. A relayed news item carries a _DESTROYED keyword, so
# status reads "destroyed", and a destroyed message with no district adopts
# whichever track is open — one such post closed a live Шахед as "знищено".
# Gated on NO DISTRICT + destroyed (rules.py::_reportage), which keeps it off
# real callouts since a first-hand sighting always localizes.
_REPORTAGE = ("повідомляють", "повідомляється", "як повідомля",
              "за попередніми даними")

# "Дорозвідка" = our side no longer sees targets of the stated type and is
# re-scanning: a temporary stand-down, NOT "it was a harmless recon drone" (a
# dictionary-meaning trap). Message-scoped, so the rules gate requires no
# district — one that names a district is a concurrent sighting.
_LOST_WORD = "дорозвід"
# The same stand-down in shorthand. Word-bounded so "чистота"/"очистити" never
# match; the rules gate also requires no district and no other-oblast scoping.
_STANDDOWN_CLEAN_RE = re.compile(r"(?<![а-яіїєґ])чисто(?![а-яіїєґ])")
# A stand-down whose next clause announces a live threat must close nothing — the
# live half wins. Curated adversatives, not bare "але" (too common in harmless
# asides).
_STANDDOWN_LIVE_THREAT = ("паралельно", "але загроза", "але триває загроза",
                          "ще виходи", "ще можливі цілі", "можливі ще цілі")

# City-wide threat: aimed at the city as a whole, no raion. During the sub-minute
# ballistic phase spotters warn the whole city before any raion is named. STRONG
# phrases are the threat signal on their own; WEAK ones also occur in news and
# need a threat word.
_CITYWIDE_STRONG = ("на місто", "над містом", "на київ", "на столиц",
                    "увага місто", "увага, місто")
# Bare "Київ!!" — the city twin of a bare district callout. Anchored to the WHOLE
# message: a loose "київ" stem would swallow every recap naming the city.
_CITYWIDE_BARE_RE = re.compile(r"^\W*(?:київ|столиця|столиці)\W*$")
# "над Києвом"/"над столицею" are WEAK even though the twin "над містом" is
# strong: all their existing corpus hits are rainbow posts. City-BOUND phrasing
# is weak for the same reason — "в напрямку Києва" also shows up in logistics
# reposts.
_CITYWIDE_WEAK = ("по місту", "по києву", "удар по києву", "по столиц",
                  "над києвом", "над столицею",
                  "бік столиці", "бік києва", "напрямку столиці", "напрямку києва",
                  "напрямок києва", "напрямку на київ")
_THREAT_CONTEXT = ("ціль", "цілі", "ракет", "баліст", "шахед", "бпла", "дрон",
                   "загроз", "удар", "приліт", "вибух", "кинджал", "іскандер",
                   "каб", "с-400", "с400", "с-300", "с300", "циркон", "пуск")

# Threat-LEVEL bulletin: commentary about a target TYPE with no target and no
# place of its own. The spotters run this as a standing side-channel beside the
# live callouts.
# RAISED -> `forecast`, QUIET -> `status`. RAISED is tested first, so a mixed
# "попередження дійсні, але поки тихо" reads as the warning.
# QUIET is emphatically NOT an all-clear: a spotter's "по балістиці тихо" must
# never close a track, it only states the situation in the feed.
_LEVEL_RAISED = ("загроза баліст", "небезпека баліст", "загроза балістики",
                 "тривога в області", "тривога у області", "тривога в обл",
                 "тривога по області", "тривога в київській обл",
                 "червоний рівень", "червоний сигнал", "підвищена загроза",
                 "підвищена небезпека", "загроза зберігається", "загроза залишається",
                 "залишається загроза", "існує загроза", "зберігається підвищена",
                 "загроза актуальна", "теж актуальна",
                 "дійсні попередження", "попередження дійсні", "попередження по",
                 "реагуємо на тривог", "реагування на загрозу", "реагуємо",
                 "залишається спорядж")
# Oblast-scope situation reports: the threat is in Kyiv OBLAST with no raion
# named — nothing to place, but it answers "is it near yet". `status`, not
# `forecast`; "тривога в області" above is the forecast half of the same family.
_LEVEL_OBLAST = ("в області", "у області", "по області", "в обл.", "області вже",
                 "областi", "в київській області", "по київській області")

_LEVEL_QUIET = ("тихо", "не видно", "без запусків", "без пусків", "пусків немає",
                "наразі немає", "поки немає",
                "не фіксується", "спокійно", "ситуація спокійна", "минула без",
                "поки все спокійно", "фальш цілі", "фальшцілі",
                # The type-scoped all-quiet: a NOTICE, never a stand-down — the
                # suppressor gate keeps a real "чисто" (lost_signal) on its own
                # type-scoped path.
                "все чисто", "наразі чисто", "поки чисто", "момент немає",
                # The negative half of the launch/carrier families below. Both
                # say the word they are about, so without these the forecast
                # branches would read a stand-down as a raised level.
                "без фіксац", "неактивн", "посадк")

# The two forecast families below are checked AFTER _LEVEL_QUIET on purpose: both
# markers routinely sit in the same sentence as an all-quiet report, and reading
# that as a raised level would be a lie in the operator's face.
#
# A LAUNCH somewhere far away, with no place of ours to map — the earliest
# warning a cruise wave gives, 30-90 min before anything reaches Kyiv. The
# negative forms are already claimed by _LEVEL_QUIET. The lookbehind keeps
# "Спуск!" (a live overhead callout) and "випуск" out.
_LEVEL_LAUNCH_RE = re.compile(r"(?<![а-яіїєґ])(?:за)?пуск(?:[иіауео]\w{0,3})?(?![а-яіїєґ])")
# ANTICIPATION of the next wave. A live callout never talks about "найближчим
# часом"; this is the sentence the operator plans the next hour around.
_LEVEL_AHEAD_RE = re.compile(
    r"найближчим часом"
    r"|можлив\w*\s+(?:\w+\s+)?(?:повторн|нов|чергов|наступн)"
    r"|(?:повторн|нов|чергов|наступн)\w*\s+хвил"
    r"|очікуєм|чекаєм"
    r"|варто реагувати"
    r"|ще діє"
)
# The WEAK half of the quiet family, checked last: "без змін" usually modifies
# something else in the same sentence rather than being the news ("Без змін,
# найближчим часом очікуємо на виліт бомбардувальників").
_LEVEL_QUIET_WEAK = ("без змін", "без критичних змін")
# "Quiet HERE, busy THERE" is the standard shape of a type bulletin. The foreign
# oblast is the contrast clause, not the subject — but `target_not_kyiv`
# (rightly, for a terse pulse) throws the whole message away over it, so an
# explicit claim of OUR scope is what tells the two shapes apart.
_OWN_SCOPE_RE = re.compile(
    r"(?<![а-яіїєґ])[ву]\s+нас(?![а-яіїєґ])"
    r"|біля києва|по києву|[ву]\s+києві|для нашого регіону|нашого регіону"
)

# Retrospective attack SUMMARY — recaps what already happened; info, never a live
# city alert. Distinguished from a live callout by an aggregate/past marker.
# "завдав удару" + "повідомили у ПС" mark the after-action bulletin, which
# otherwise parsed as a fresh impact.
# "попередньої атаки"/"було атакован" are the ANALYTIC past frame and belong HERE
# rather than in _RETROSPECTIVE, because the damage is a CITY-WIDE alert: "на
# київ" matched inside the past clause and raised a live ballistic threat over
# the whole city with nothing in the sky. `summary` is what _citywide and
# should_fallback both exclude, so it fixes the alert and the paid call at once.
# "застосував" was REJECTED: it buys nothing these don't already get and would
# newly surface a Zaporizhzhia strike report and two forecasts.
_SUMMARY = ("загалом", "всього", "за останні", "випустил", "під час",
            "завдав удар", "завдали удар", "завдано удар",
            "повідомили у пс", "повідомили у повітр",
            "попередньої атаки", "було атакован")

# Softer past-strike aggregate. Separate from _SUMMARY because "вдарил" also
# appears in a single live strike ("ракета вдарила по Троєщині"), so these count
# ONLY when no raion is named (rules.py::_summary). "застосован" is the same
# register and stays district-gated because its one district-bearing hit is a
# real localized impact; the present tense "застосовує" doesn't share the stem.
_SUMMARY_NO_DISTRICT = ("вдарил", "застосован")

# Every link-bearing message in the corpus is promo/donation/ad/meta, never a
# live callout — a spotter's sighting never carries a link.
_LINK_MARKERS = ("http", "t.me/")
# The link-less donation variant.
_CARD_NUMBER_RE = re.compile(r"(?<!\d)\d{16}(?!\d)")
# The link-less, card-less ad variant (a bar ad that resolved to Харків once that
# oblast had a gazetteer). The country code is required — a bare ten-digit run is
# not rare enough to suppress on.
_PHONE_RE = re.compile(r"\+?38[\s\-]?0\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}(?!\d)")
# The link-less channel ad: a subscribe post listing localities, and the @-handle
# sign-off that rides one channel's recurring situation-map caption (whose bare
# "БпЛА" types it and buys a triage call every time).
_AD_RECRUIT = ("тепер в telegram", "тепер у telegram", "якщо ти живеш у",
               "підписуйс", "підписуйтес", "підтримати канал")
# The link-less, card-less donation/engagement post — a fundraiser scoreboard and
# audience call-and-response whose sign-off keeps it threat-flavoured. Phrases are
# the scoreboard/engagement frames themselves, never the sign-off, so a real
# callout in the same register is untouched.
_ENGAGEMENT = ("підтримало збір", "підтримали збір", "підтримало тільки",
               "підтримала лише", "підтримав лише", "підтримало лише",
               "хто не пройде повз", "хто не ігнорує", "дайте реакцію",
               "дайте реакції", "дивитесь футбол", "буде зі мною", "люблю цілую")

# Decoy / EW — a modifier on the attack (attack.py::classify), NOT a replacement
# classification: a raid can be combined AND partly imitation. "реб" is 3 letters
# and collides, so it lives in rules._WHOLE_WORD like "каб". Behavioural
# inference ("every track vanished with no impacts" => decoy) is deliberately NOT
# done — a hint for a human, not a classifier signal.
_DECOY = ("імітаці", "реб", "реби", "обманк", "хибн", "фальшив")

# A flag on the attack (has_hypersonic), deliberately not a 6th target_type,
# which would spread into evals/icons/severity for one rendering need.
# "кинджал"/"аеробаліст" already type ballistic via _BALLISTIC.
_HYPERSONIC = ("кинджал", "циркон", "аеробаліст")

# Case endings stripped (longest first) to reduce a word to a rough stem, so one
# regex matches most forms. The adjectival "-ськ/-цьк" root is deliberately KEPT
# (only "ий"/"ого"/"их" come off after it), so a raion adjective (Оболонський)
# stays distinct from the noun (Оболонь).
_SUFFIXES = ("ого", "ому", "ій", "ої", "ою", "их", "ий", "им", "ах", "ям",
             "ам", "ів", "ь", "и", "а", "я", "у", "ю", "і", "е", "о")

_APOSTROPHES = "'ʼ`’‘"

# A raion adjective is also part of real street names ("Оболонський проспект"),
# so a district stem adjacent to one of these is a street and DistrictMatcher
# discards it. "метро" is here for the same reason: Kyiv names stations after
# far-away cities, and the station is a Kyiv landmark, not the city.
_STREET_WORDS = ("проспект", "вулиц", "вул", "провулок", "бульвар", "узвіз", "шосе",
                  "набережн", "площ", "метро")

# Gazetteer entries that are a CITY sharing its name with an OBLAST: for these the
# adjectival form is the oblast, never the city. An explicit registry rather than
# a general "-ськ- in the tail" rule, because for most entries the adjective IS
# the place. Not gated on `RegionSpec.active` — the veto only fires when a
# gazetteer entry for the city exists, so gating would be dead code with a footgun.
_OBLAST_CITY_STEMS = frozenset(
    stem for spec in REGION_SPECS for stem in spec.oblast_city_stems
)

# Gazetteer aliases that must match as WHOLE words with no case tail — the same
# discipline rules._WHOLE_WORD uses for "каб"/"реб". Two reasons to be here: an
# alias below DistrictMatcher's 4-char stem floor (dropped silently otherwise), or
# one whose stem collides with an everyday word ("остер" fires inside
# "остерігайтеся", "троя"/"троєю" reach "троянди" and the numeral "троє").
# A whole-word alias carries no case tail, so every form the corpus uses is listed
# separately. GAZETTEER.md records the collision behind each entry — read it
# before touching one. Keep this set tiny: only forms spotters really use as a
# standalone toponym.
_WHOLE_WORD_ALIASES = frozenset({"чзв", "пох", "бц", "голос", "пущею",
                                 "море", "моря", "морі", "морю", "остер",
                                 "віта",
                                 "копита", "красне", "лісне", "козари",
                                 "вербове", "артеменків",
                                 "центр", "центру", "центрі",
                                 "антонов", "антонова",
                                 "заспа", "заспу", "заспи",
                                 "гути",
                                 "березна", "березну",
                                 "тец",
                                 "замістя", "розсудів",
                                 "прогрес",
                                 "суми", "сум", "сумах", "сумами",
                                 "терни",
                                 "крут",
                                 "перемоги",
                                 "тополя", "тополю",
                                 "сад", "сади",
                                 "зелений",
                                 "блакитні", "старе",
                                 "річки",
                                 "лівий", "лівим", "лівому", "лівого",
                                 "правий", "правим", "правому", "правого",
                                 "золоті",
                                 "гес",
                                 "русанівські",
                                 "троя", "трої", "трою", "троєю",
                                 "мирне", "максим"})

# An alias that is also part of a PROPER NAME, keyed to the word that follows it.
# "Голос Києва" is a Telegram channel other channels quote, not a callout over
# Holosiivskyi; "центр спеціальних операцій" is an institution, not the middle of
# the city. The toponym stays, its collision is resolved by the adjacent word.
_ALIAS_NEXT_WORD_VETO: dict[str, tuple[str, ...]] = {
    "голос": ("києва", "кієва"),
    "центр": ("спеціальн", "міжнародн", "дослідж"),
    "центру": ("спеціальн", "міжнародн", "дослідж"),
    "центрі": ("спеціальн", "міжнародн", "дослідж"),
}

# The mirror image: an alias that only counts when the PRECEDING word starts with
# one of these. "церкв" is Біла Церква's only matchable word (a spaced name never
# becomes one stem), but alone it would read "приліт у церкву" as a callout 80 km
# south; "перемоги" is an ordinary noun and also a village.
_ALIAS_PREV_WORD_REQUIRED: dict[str, tuple[str, ...]] = {
    "церкв": ("біл",),
    "перемоги": ("просп", "пропесп"),
}

# There is deliberately no global PREV_WORD_VETO. It existed for one case — two
# entries sharing their only matchable word, where the rule that saves one must
# not touch the other — which a dict keyed by matched text cannot state. Write a
# new one as `match_context` on the entry (see matcher.MatchContext), not here.

# The third of the set: an alias that counts only when the word AFTER it starts
# with one of these. It is what makes a spaced name shippable when the
# DISTINCTIVE half is the first word and the second is generic — `_stem` strips
# spaces, so "зеленийгай" never appears in text, and "зелений"/"блакитні"/"старе"
# alone are the ordinary-adjective class GAZETTEER.md rejects.
_ALIAS_NEXT_WORD_REQUIRED: dict[str, tuple[str, ...]] = {
    "зелений": ("гай",),
    "блакитні": ("озер",),
    "старе": ("сел",),
}

# Everything above as one word-start stem set, consumed by `toponyms.py` to answer
# "is this word already something the parser knows about?" — a word the vocabulary
# explains is never a missing gazetteer entry. Assembled here rather than
# re-listed there, so a stem added above is automatically excluded from the
# coverage-gap queue too.
# Multi-word phrases are kept out: these are matched against single tokens.
NON_TOPONYM_STEMS: frozenset[str] = frozenset(
    stem
    for stem in (
        *_BALLISTIC, *_MISSILE, *_JET, *_JET_MODEL, *_UAV,
        *_CLEAR, *_DESTROYED, *_UNCONFIRMED, *_CONFIRMED, _UNSCOPED_CLEAR_WORD,
        *_NEW_TARGET, *_MOVEMENT_CUE, *_PULSE_WORD,
        *_THREAT_CONTEXT, *_AFTERMATH, *_CIVIC_NOTICE, *_REPORTAGE,
        *_IMPACT, *_POWER_OUTAGE, _SIREN_WORD, _LOST_WORD, _DAY_RECAP_WORD,
    )
    if " " not in stem
)

# The same vocabulary that must be matched as WHOLE words, never as prefixes —
# which is how the parser itself uses them. Ukrainian place names begin with them
# often enough that treating them as stems is a live hazard: "три" heads
# Трипілля, "троє" Троєщина, "семи" Семиполки, "пара" Парафіївка, "кияни"
# Кияниця, "пост" Постольне.
NON_TOPONYM_WORDS: frozenset[str] = frozenset(_NUM_WORDS) | {
    "пара", "пари", "пару",
    "кияни", "киян", "киянам", "киянами", "киянка", "киянин",
    "пост", "пости", "постів", "постом",
}

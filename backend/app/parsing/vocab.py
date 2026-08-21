"""Curated Ukrainian keyword/phrase vocabulary and regex literals for the rule
parser (see `rules.py`). Pure data — no matching/decision logic here.

Every list below is narrow on purpose. Where a comment says a word was REJECTED
or is gated, that is a recorded corpus finding — widening it there has broken
the live map before.
"""

from __future__ import annotations

import re

# --- Target type keywords (checked in priority order) ---
# Ballistic first: sub-minute flight, and it must beat the generic "ракет" in the
# same message. A distinct type from cruise because it drives different output —
# ballistic is city-wide with no trajectory, cruise draws a spotter-tracked
# vector. С-300/400 fly surface-to-surface at cities, so they belong here.
# "Циркон" too: same un-spottable profile, and a channel that only said
# "циркони" produced a night of `unknown` tracks (07-18). "КН-23" is
# Iskander-class quasi-ballistic — ballistic, but NOT _HYPERSONIC; both
# spellings appear in the feed.
_BALLISTIC = ("баліст", "іскандер", "кинджал", "кн-23", "кн23", "с-400", "с400",
              "с-300", "с300", "аеробаліст", "циркон", "гіперзвук")
# Cruise/guided-bomb/generic, split by how SPECIFIC the identification is.
# A named cruise weapon pins down what is flying as precisely as any ballistic
# stem does; the bare generic "ракет" is what a spotter drops between two
# ballistic toponyms and means nothing on its own (only an explicit ballistic
# marker above promotes it). That distinction decides whether a message may
# correct a channel's ballistic type context — see
# ingest/context.py::_note_and_inherit_type.
_MISSILE_NAMED = ("крилат", "калібр", "х-101", "х-59", "х-22")
_MISSILE_WEAPON = ("ракет", *_MISSILE_NAMED, "каб", "авіабомб", "керован авіа")
# Strategic aviation IS the cruise-missile threat, and the spotters name the
# CARRIER instead of the weapon: "пуски зі стратегічної авіації", "пуски ракет
# із ТУшок", "виліт групи Ту-95МС", "в повітрі: 7 Ту-95, 2 Ту-160". Those
# messages typed as `unknown`, and an untyped message can never become a
# threat-level notice (rules.py::_level_notice) — so the earliest warning a
# cruise wave gives, hours of it, surfaced nowhere at all.
#
# Kept separate from the weapon stems because a carrier says nothing about what
# is over a raion RIGHT NOW: a bomber leaving Olenya is four hours from
# launching, so this must not become the channel's live target-type context
# (ingest/context.py::_note_and_inherit_type).
# "тушок" is the genitive plural with a fleeting vowel (туш-о-к), so the "тушк"
# stem does not reach it — both forms are listed. 8 of the 38 real mentions.
_MISSILE_CARRIER = ("стратегічн авіац", "стратегічної авіа", "тушк", "тушок",
                    "ту-95", "ту95", "ту-160", "ту160", "бомбардувальник")
_MISSILE = _MISSILE_WEAPON + _MISSILE_CARRIER
# Named JET models. Checked BEFORE _MISSILE, for the same reason ballistic is:
# one night's feed called С8000 «Бандероль» a «ракета», a «баражуючий
# боєприпас» and a bare «бандероль» — and the generic "ракет" would win the
# priority chain and label it cruise.
#
# It is formally a small cruise missile with a jet engine, but on this map the
# type means how the target BEHAVES: ~620 km/h, manoeuvres, and the northern
# spotters track it position by position, which is exactly the jet-drone
# profile the vector rendering is built for. 14 callouts in one night
# (2026-08-19) stayed `unknown` before it was listed at all.
_JET_MODEL = ("бандерол",)
# Bare "реактив", not "реактивн" — the noun form is used too ("3 реактива повз
# Славутич"); on 08-04 those stayed unknown and inherited ballistic.
_JET = ("реактив", "швидкісн")
# "баражуюч"/"баражаюч" = loitering munition, both spellings in the feed. It is
# the generic class word the alert channel uses when it names no model
# ("двом баражаючим боєприпасам"); with a model named, the more specific list
# above wins the priority chain.
_SHAHED = ("шахед", "shahed", "мопед", "герань", "герані", "дрон", "бпла",
           "безпілотник", "безпілотн", "баражуюч", "баражаюч")

# Gender fallback: a bare masculine numeral implies a drone, since шахед/дрон/
# БПЛА are masculine and "ракета" is feminine ("Один на водосховище"). Corpus:
# 6/6 real target-count messages, zero counter-examples. Feminine "одна"/"одне"
# REJECTED — every real hit was casualty news agreeing with "людина"/"тіло", and
# a generic "одна ціль" would collide. Jets are excluded because spotters always
# say "реактивний" explicitly (caught by _JET), so a bare "один" is the default.
_MASC_ONE_RE = re.compile(r"(?<![а-яіїєґ])(?:один|одне)(?![а-яіїєґ])", re.IGNORECASE)

# --- Status keywords ---
_CLEAR = ("відбій",)
# "Чекаємо відбій" ANTICIPATES the all-clear, it is not one — the bare "відбій"
# stem would read these as a real clear and close every open track. Curated
# phrases, not the bare "чека"/"очіку" stems (a genuine clear says "дякуємо за
# очікування"). Includes infinitive/genitive forms and the predictive
# "скоро/надія на відбій" (a real clear says "Дали відбій", never that).
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
# The SIREN itself ended ("Відбій тривоги") => the clear is unscoped, even if a
# target type is also named. Gates clear_scope: ballistics never carry a Kyiv
# district, so "По балістиці відбій" would otherwise look like a full all-clear
# and close unrelated tracks (real case: "тривога зберігається по цих БПЛА. По
# балістиці відбій.").
_UNSCOPED_CLEAR_WORD = "тривог"
# "мінус" = spotter shorthand for a downed target; substring-safe in this feed.
_DESTROYED = ("збил", "збито", "знищ", "нейтраліз", "уражен", "ліквідов", "впав",
              "мінус")
_UNCONFIRMED = ("уточнюється", "непідтвердж", "не підтвердж", "попередньо", "можливо")
_CONFIRMED = ("підтвердж", "🔴")

# Small counts are written as WORDS about as often as digits, and until now the
# counting rules below were digit-only, so every one of them was read as a single
# target: "ШІСТЬ БАЛІСТИК НА КИЇВ!", "‼️П'ЯТЬ ЦІЛЕЙ НА КИЇВ!", "Ще два Циркони на
# столицю", "Три реактивні «Шахеди»". 97 real messages spell a count this way and
# 39 of them became located tracks that then showed ×1 on the map — the same
# undercount reached `incident.target_count`, so the attack banner and the
# journal inherited it.
#
# Apostrophe-less spellings only: `normalize` strips apostrophes, so "п'ять"
# reaches these patterns as "пять". Stops at ten: past that spotters use digits,
# and the long forms ("двадцять три") would need real number parsing.
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
    # "both" is a count word too — "Уважно по групі одній, обидва реактивні".
    # Listed on purpose: it ENDS in "два"/"дві", so without an entry of its own
    # it would have been counted anyway, by the accident of a suffix match.
    "обидва": 2, "обидві": 2, "обох": 2,
}
# Longest-first, so "двоє" can't be shadowed by "два" (and "обидва" not by "два").
_NUM_WORD_ALT = "|".join(sorted(map(re.escape, _NUM_WORDS), key=len, reverse=True))
# Either form. The word branch carries its own word-START guard: the trailing
# `\s+` every caller adds already stops a numeral matching the HEAD of a longer
# word ("три" in "тривога"), but nothing stopped it matching the TAIL of one, and
# `_COUNT_NOUN_RE` has no lookbehind of its own. The guard is inside the branch
# rather than on the whole pattern so the digit form keeps matching exactly what
# it matched before.
_NUM = rf"(?:\d+|(?<![а-яіїєґ])(?:{_NUM_WORD_ALT}))"
_NUM_SHORT = rf"(?:\d{{1,2}}|(?<![а-яіїєґ])(?:{_NUM_WORD_ALT}))"


def count_value(token: str) -> int | None:
    """An int from either a digit run or a numeral word, else None."""
    return int(token) if token.isdigit() else _NUM_WORDS.get(token)


# --- New-target markers (start a fresh track) ---
_NEW_TARGET = ("новий", "нова ціль", "ще один", "ще одна", "інша ціль",
               "друга ціль", "додатков", "нові цілі")
# "ще N <noun>" — additional targets. Noun-anchored, not bare "ще N", so a
# time reference ("ще 20хв") never matches.
# The type ADJECTIVES and named weapons belong here for the same reason they do
# in _COUNT_NOUN_RE: "Ще два реактивні чмошника на Сеньківку" is as much an
# additional-targets callout as "ще 2 БпЛA", and the noun a spotter picks after
# the adjective is unpredictable.
_NEW_TARGET_COUNT_RE = re.compile(
    rf"ще\s+{_NUM}\s+(?:ракет|ціл|шахед|бпла|дрон|баліст|реактивн|крилат|циркон|калібр)",
    re.IGNORECASE,
)

# Count shorthand: a number then х/x ("2х", "їх вже 3х"). The lookahead drops
# "20хв" and numbers glued to words. This is the size of ONE group flying
# together — it annotates the track, it never fabricates N tracks.
_COUNT_RE = re.compile(r"(\d+)\s*[хx](?![а-яіїєґa-z])", re.IGNORECASE)
# A number directly qualifying a target noun ("3 ракети", "2 цілі").
#
# The type ADJECTIVES belong here as much as the nouns do: spotters put the
# number in front of them ("10 реактивних Шахедів на Бровари", "До 10 крилатих
# ракет", "2 калібри залишилось"), and since the digit isn't adjacent to the
# noun those 33 real messages lost their count entirely — a located track that
# should have shown ×10 showed ×1.
# "циркон" sits here with "калібр" for the same reason — a named weapon a
# spotter counts directly ("Ще два Циркони на столицю").
_COUNT_NOUN_RE = re.compile(
    rf"({_NUM})\s+(?:ракет|ціл|шахед|бпла|дрон|баліст|реактивн|крилат|калібр|циркон)",
    re.IGNORECASE,
)
# A bare number heading for a place: "3 на Славутич", "2 на Бровари", "Ще 4 на
# Бровари", "2 курсом на Центр". Spotters count targets this way constantly and
# neither the "3х" nor the "3 ракети" form covers it — 9 real messages lost their
# count entirely.
#
# Deliberately only HALF the rule: the caller additionally requires a
# gazetteer-matched place to start where this match ends (rules.py::_target_count).
# A bare digit before a preposition alone is a minefield — "Ту-22м3 на Київщину"
# would read as 3 targets. The lookbehind rejects a digit glued to a word or to
# another number ("22м3") and time-ish forms ("о 3:00", "3.5").
_COUNT_TO_PLACE_RE = re.compile(
    rf"(?<![0-9а-яіїєґa-z:.,])({_NUM_SHORT})\s+"
    r"(?:на|над|до|біля|курсом\s+на|у\s+напрямку(?:\s+на)?)\s+",
    re.IGNORECASE,
)
# A number that is DOING something: "Знову 3 долітають до Броварів", "Ще 4
# летить". The verb is the anchor here — a place can sit several words away, or
# be absent entirely, so the place-anchored form above can't reach these.
#
# PRESENT TENSE ONLY, and that is the guard: "3 летять" is a live callout, while
# the past tense is the voice of recaps and news ("30 ракет летіли", "випустила
# 8 балістичних ракет") — those numbers are salvo totals for a whole night, and
# stamping one on a district track is what once had the journal reporting
# hundreds of phantom targets. Verified against the whole real corpus: 3 matches,
# all of them genuine live counts, zero false positives.
_COUNT_MOVING_RE = re.compile(
    rf"(?<![0-9а-яіїєґa-z:.,])({_NUM_SHORT})\s+"
    r"(?:долітаю|долітає|летят|летить|йдут|ідут|іде\b|рухаю|сунут|заходят|прямую|проходят)",
    re.IGNORECASE,
)

# Terse target/launch "pulse" with no location ("Ціль!", "Ще вихід", "3 ракети").
# Too terse to localize alone; only acted on during an open city-wide alert.
# "вихід" = a launch callout here. The 07-18 additions are the words spotters
# actually shouted between toponyms while everything above stayed silent.
_PULSE_WORD = ("ціль", "цілі", "вихід", "ракет", "баліст", "шахед", "бпла", "дрон",
               "циркон",
               "цілей",   # genitive — "ціль"/"цілі" don't substring-match it
               "пуск",    # "Ще пуски!"
               "пада",    # "Падають!" — live incoming
               "летить", "летять",
               # The type ADJECTIVES spotters use on their own, with the noun
               # left implicit: "2 реактивні", "Крилаті", "По калібрам". Each
               # one used to fall through to "без району" AND buy a full LLM
               # call (~$0.006) that could only answer "noise" — 6 of the 33
               # calls on the night of 2026-08-20.
               "реактивн", "крилат", "калібр")

# --- Pulse guard: a pulse corroborates the KYIV city alert, so it must not name
# a place we can't recognize. A word right after one of these prepositions is in
# TARGET position ("біля Пирятина", "На короп крилаті") — if the gazetteer
# didn't match it, the message is about somewhere we don't know and pulsing it
# would credit a Kyiv track with someone else's sighting (the T2445 class).
# FROM-position prepositions (з/зі/від) are deliberately absent: an origin is
# legitimately ours and already pulses ("Балістика з Курщини", "Ціль зі
# Сумщини"). ---
_PULSE_TARGET_PREP = ("на", "над", "до", "біля", "під", "по", "у", "в")
# Kyiv itself is not an unknown place: "Ракети до Києва!" pulses and must keep
# doing so. Target vocabulary ("По калібрам") is allowed by the caller.
_PULSE_PREP_KNOWN = ("київ", "києв", "столиц", "міст")

# --- Standby: the raions a spotter puts on notice for a target that has NOT
# reached them. One message routinely carries both claims — «Пухівка/Зазимʼя 🔴
# та готовність Бровари», «Рожни/Пухівка 🔴. Троя готовність.» — and the parser
# used to flatten them, so the standby raion joined the track with the SAME
# confirmed status as the two the spotter actually saw a target over.
#
# "Увага"/"уважно" deliberately do NOT belong here: 111 of the 136 real messages
# carrying them are plain target callouts («Увага Троя 🔴.»), so treating them as
# a warning frame would gut the feed. «Готовність» is the marker that means it. ---
_READINESS_RE = re.compile(r"(?<![а-яіїєґ])(?:готовн|поготов|приготуй)[а-яіїєґ]*")
_SENTENCE_END_RE = re.compile(r"[.!?\n]")
# A gazetteer hit's own word, to find where it ends (DistrictHit carries only its
# start offset), and the connectors that make several hits ONE coordinated list
# ("Район Обухова/Василькова/Фастова готовність" — all three are on standby).
_TOPONYM_WORD_RE = re.compile(r"[а-яіїєґ'’ʼ\-]+")
_LIST_JOIN_RE = re.compile(r"^[\s/,]*(?:та|і|й)?[\s/,]*$")

# --- Movement cues: mark a multi-district message as ONE target on a route
# ("через Броварський район", "курсом на Троєщину") rather than an enumeration of
# simultaneous targets ("Вишневе Жуляни"). On 07-18 every enumeration glued its
# districts onto one track, recreating the zigzag mega-track. ---
_MOVEMENT_CUE = ("курс", "у бік", "в бік", "через", "прямує", "рухаєт", "повз",
                 "напрям", "заходить", "захід у", "летить на")
# A district in a prepositional phrase is a located frame, not an enumeration
# item ("удар по Оболоні", "над Оболонню").
_PREPOSITION_BEFORE_DISTRICT = ("на", "у", "в", "до", "з", "зі", "із", "над",
                                "біля", "під", "по")

# --- Aftermath: the RESULT of a strike (casualties, damage, rescue) is news
# about a place, not a live target, even when it names a district. ---
_AFTERMATH = ("постраждал", "загинул", "поранен", "жертв", "уламк", "пошкодж",
              "зруйнов", "врятув", "рятувальник", "надзвичайник", "дснс",
              "багатоповерхів", "наслідк", "кмва", "госпіталіз", "медик",
              "евакуй", "загибл", "потерпіл",
              "пожеж",
              # Post-strike fire. Stems picked to avoid collisions:
              # "горіл"/"згорі" ⊄ "Вишгород", "горять" ⊄ "говорять".
              "горить", "горять", "горіл", "згорі",
              # Full forms, NOT the stem "пала" — "ракета впала" contains it and
              # must keep its live meaning. ("Вся Лукʼянівка палає" raised a live
              # ballistic track on 07-19.)
              "палає", "палають", "палала", "палало",
              "відновленн")

# --- Our air defence engaged ("Відпрацювали установки по Дарницькому та
# Соломʼянському", "працює ППО") — not an incoming target, and matching its two
# districts would draw a bogus vector between them. ---
_AD_ACTION = ("відпрацюв",
              "працює ппо", "ппо працює", "працює наша ппо", "сили ппо", "робота ппо")

# --- Civic notices the channels reprint (transport routes, road closures). They
# name streets/neighbourhoods the gazetteer matches but are city news — the
# T217/M668 FP class. Bare "маршрут"/"рух"/"транспорт" are deliberately absent:
# a real target "змінила маршрут руху". Only transport-mode words and multiword
# traffic phrases are safe (validated absent from real sightings). ---
_CIVIC_NOTICE = ("тролейбус", "трамвай", "маршрутк", "фунікулер", "автобус",
                 "громадського транспорт", "громадський транспорт",
                 "дорожнього руху", "рух транспорт", "руху транспорт",
                 "організації руху", "обмежать рух", "обмежуватимуть рух",
                 "перекрито рух", "перекрито середню",
                 # Street closures announced for a visiting delegation read
                 # exactly like a transport notice and name the place the same
                 # way: "❗️Частково перекриють центр Києва завтра. Обмеження
                 # запроваджуються у зв'язку з проведенням охоронних заходів за
                 # участю іноземних делегацій" (raw 2816) — which, the moment
                 # «Центр» became a known place, started raising a track over
                 # the middle of the city.
                 "перекриють", "обмеження запровадж", "охоронних заход",
                 # Scheduled utility works — the same class as transport news:
                 # a neighbourhood named in a plumbing/repair announcement
                 # ("У житловому масиві Пуща-Водиця … під час виконання
                 # ремонтних робіт можливе зниження тиску у водопостачанні",
                 # raw 1371, which was raising a track).
                 "водопостачанн", "водогін", "ремонтних робіт", "ремонтні роботи",
                 "планові роботи", "зниження тиску", "профілактичн",
                 # City-services news in the same register — it names beaches,
                 # lakes and neighbourhoods ("🏖 На більшості пляжів Києва вода
                 # відповідає нормам … у Пущі-Водиці", raw 1724).
                 "пляж", "водойм", "відповідає нормам", "якість води")

# єППО = the crowd-sensor app. Spotters relay its marks while dismissing them as
# unverified. Suppress only when an єППО mention is PAIRED with a dismissal cue,
# so "єППО показує ціль на Троєщині, підтверджую" survives. _EPPO_WORD covers
# the Cyrillic-є spelling and the common Cyrillic-е typo.
_EPPO_WORD = ("єппо", "еппо")
_EPPO_DISMISS = ("не видно", "не бачим", "не фіксу", "не спостеріга", "дорозвідк",
                 "хибн", "локаційно чист")

# --- Impact: a LOCALIZED hit whose location is worth mapping, as opposed to
# generic aftermath news. Needs a district — "є влучання десь" places nothing.
# When impact verbs and aftermath words co-occur, impact WINS (the location is
# the useful signal). "пошкодж"/"зруйнов" are also in _AFTERMATH, so without a
# district they still suppress. "влучил" covers влучила/влучило/влучили — on
# 07-18 Кличко's "Балістика влучила прямо в багатоповерхівку у Шевченківському"
# had no noun form, the aftermath stem won, and a real strike never reached the
# map. ---
_IMPACT = ("влучанн", "влучил", "приліт", "пошкодж", "зруйнов")

# Retrospective footage/report of a PAST strike — not a fresh hit. Blocks the
# impact reading only (the message falls back to aftermath suppression); it does
# NOT block a citywide reading — see _SUMMARY for the phrases that must.
_RETROSPECTIVE = ("на відео", "останньої атаки", "минулої атаки", "нічної атаки",
                  "вчорашн", "минулої ночі")

# --- Grid outages say "пошкодж" next to districts, which `_impact` otherwise
# reads as a confirmed hit and pins a phantom marker. Blocks impact unless an
# unambiguous strike word (влучанн/приліт) is present too. Grid-specific stems,
# not bare "світл", so a building strike mentioning lights survives. ---
_POWER_OUTAGE = ("електропостачанн", "електроенерг", "електромереж", "енергетик",
                 "енергооб", "знеструмл", "підстанці", "обленерго", "дтек",
                 "аварійне пошкодж", "немає світл", "нема світл", "без світл",
                 "зникло світл", "відключенн світл")

# --- Explicit denial ("Не йде на Оболонь"). Curated phrases, not bare "не" —
# that would swallow "не підтверджено" (a different status). LIMITATION:
# message-scoped, so a message that both denies one target and reports another
# live one would be dropped whole; no such shape seen in the feed yet. ---
_NEGATION = ("не йде", "не летить", "не рухається", "не курсом", "не в бік",
             "не фіксується", "не спостерігається", "не зафіксовано",
             "без загроз", "поза загрозою")

# --- Conditional/speculative hedge — a possible future event, not a sighting.
# Corpus findings: bare "якщо" is UNSAFE (it appears in a live sighting as a
# distance qualifier, "5/8 хвилин до області, якщо по прямій"), so it needs a
# consequence verb alongside — clean across all 18 real hits. Bare "у разі" is
# unsafe too: the idiom "у жодному разі" occurs twice, hence the exclude list.
# "якщо піде"/"може піти" had zero hits — kept as forward cover, verb-anchored.
_CONDITIONAL_PHRASES = ("якщо піде", "може піти")
_CONDITIONAL_IDIOM_EXCLUDE = ("жодному разі", "жодним разі")
_CONDITIONAL_CONSEQUENCE = ("очіку", "відбудеться", "відбуватимуться")

# --- Preparatory/forecast advisory ("Росія готує удар балістикою по Києву") —
# a planned future strike, not one in flight. Same treatment as the hedges above.
# Corpus findings: "готу" is safe as a bare stem WHEN gated on a weapon word
# (_THREAT_CONTEXT); an ungated live shorthand ("готується знову Троя") then
# correctly keeps its district. "план" is NOT safe even gated — "Кияни,
# плануйте день…" pairs a reader-facing imperative with a real live weapon word
# two clauses later, so only 3rd-person "планує"/"планують" (always the enemy)
# is used. "може застосув" is kept as a two-word phrase, not the bare stem,
# which would collide with the live "загроза застосування балістики".
_FORECAST_VERB = ("готу", "планує", "планують", "може застосув", "можуть застосув")

# --- Night/evening forecast ("На цю ніч загроза по балістиці актуальна") — a
# heads-up about a coming night; the "по Києву" inside one raised a live citywide
# ballistic alert (raw 1771). The register is nominal, so the anchor is the
# timeframe phrase, gated on a weapon word. Corpus: ~10 hits, all forecasts.
# "вночі" REJECTED — too broad, collides with aftermath recaps.
_FORECAST_TIMEFRAME = ("на сьогоднішню ніч", "на цю ніч", "цієї ночі", "на ніч",
                       "протягом ночі", "на вечір", "найближчими ноч")

# --- "можуть бути" as a bare hedge is UNSAFE: a real strike report with real
# casualties uses it for an unrelated clause ("під завалами можуть бути люди"),
# and a bare match would wipe that correct impact marker. Anchored to a
# following explosion/strike noun instead.
_HEDGE_MODAL_RE = re.compile(r"(?:можуть бути|може бути)\s+(вибух|обстріл|удар|приліт|пуск)")

# --- Advisory / relayed-opinion preview of which raions MIGHT be hit — second-
# hand or forecast, not first-hand. Three real shapes (all 07-23): relayed rumour
# ("Пишуть що також є загроза для Броварів"), relayed speculation ("в інших
# джерелах … ворога цікавлять такі райони: …"), warning bulletin ("Є
# попередження про використання 35 балістичних ракет … Підвищена загроза таким
# районам: …"). Each listed gazetteer raions and raised live dots for targets not
# in flight. Routed through the conditional-hedge path.
#
# These phrases are self-sufficient (corpus: they appear ONLY in this class).
# The nominal "підвищена загроза" and "ворога цікавлять" markers need a weapon
# word — handled in rules._has_conditional_hedge — because "підвищена загроза"
# also occurs in an air-pollution notice. "за даними" (5 hits, all news/recap/
# forecast), "до застосування"/"підвезенн" (enemy-side stockpile reports, 9+3
# hits) and "маю інформац" (2 intel relays) carry the class alone: none is ever
# a first-hand callout. ---
_ADVISORY_RELAY = ("пишуть що", "пишуть, що", "інших джерелах", "є попередження про",
                   "за даними", "до застосування", "підвезенн", "маю інформац")

# --- Recon-analysis prose ("Ворог здійснив серію розвідувальних заходів… у
# фокусі противника опинилися Фастівський район, Вишгород…") — an intelligence
# write-up, not a callout. It names raions (the recon focus), so unsuppressed it
# raised phantom tracks AND its "крилатих ракет" seeded a false `missile` type
# that bled onto terse callouts via inheritance (07-31, incident 153). Gated on a
# weapon word; every marker is 0-hit in the real spotter corpus. ---
_RECON_ANALYSIS = ("у фокусі противник", "розвідувальних заход", "опрацюванн",
                   "приділяє")

# --- Siren echo ("Тривога у Вишгородському районі"): a district but no target
# type at all. A real sighting here always states a type, so "type unresolved +
# тривога" isolates the echo without a shape-specific regex. ---
_SIREN_WORD = "тривог"

# --- Day recap ("Знову Деснянський район під атакою сьогодні"): a district, no
# live type or vector. "сьогодні" also appears in real sightings, so this only
# lowers confidence and KEEPS the district — safer than suppressing. ---
_DAY_RECAP_WORD = "сьогодн"

# --- Buzz-slang: "бджілки"/"бджоли" = OUR drones over enemy territory, so the
# message is reassurance chatter. Corpus: all 3 hits are commentary. One carried
# "реактивні", which typed the channel context as jet_drone and a citywide
# ballistic callout 26s later inherited it — the main city card of the 07-24
# salvo stuck at «БпЛА». So buzz-slang must not set/consume the per-channel type
# context (ingest._note_and_inherit_type). ---
_BUZZ_CHATTER = ("бджілк", "бджол")

# --- Political/official quote naming a place ("У Вишневому був склад
# боєприпасів... — Зеленський") — a news repost, not a sighting; about WHO is
# speaking, unlike siren_only/day_recap. Marker: dash + named official. Corpus:
# only 2 hits (both the same Вишневе/Зеленський story), so a curated name list
# is proportionate — a generic "dash + capitalized surname" regex would be far
# riskier without more real examples. ---
_QUOTE_ATTRIBUTION_RE = re.compile(
    r"[—-]\s*(президент\w*|зеленськ\w*|сирськ\w*|кличк\w*|ігнат\w*|умєров\w*|"
    r"буданов\w*|малюк\w*|генштаб\w*)",
    re.IGNORECASE,
)

# --- Second-hand reportage ("Повідомляють про знищення в Сибіру ешелону…" —
# raw 6097). A relayed news item carries a _DESTROYED keyword, so status reads
# "destroyed", and a destroyed message with no district adopts whichever track is
# open: on 2026-08-14 this post closed T3332 — a live Шахед over Київське
# водосховище — as «знищено» while it was in fact continuing west.
#
# Gated on NO DISTRICT + destroyed (rules.py::_reportage), which is what keeps it
# off real callouts, since a first-hand sighting always localizes. Corpus (4242
# unique): 14 messages carry a marker, only 2 surface at all ("Гатне
# повідомляють про приліт", the Ворзель/Ірпінь/Буча recon drone) and BOTH name a
# raion; with the status gate exactly 1 message changes — raw 6097 itself.
# Deliberately NOT fixed by adding "сибір" to _OTHER_OBLAST: the class is the
# relayed register, and a geography list needs a new entry per region. ---
_REPORTAGE = ("повідомляють", "повідомляється", "як повідомля",
              "за попередніми даними")

# --- "Дорозвідка" = our side no longer sees targets of the stated type and is
# re-scanning: a temporary stand-down, NOT "it was a harmless recon drone" (a
# dictionary-meaning trap, confirmed with the user). Message-scoped, so a message
# that ALSO names a district is a concurrent sighting and must not be swallowed —
# the rules gate requires no district. Corpus: 21 of 23 real hits match cleanly,
# 1 has a district (correctly excluded), 1 resolves via "відбій". ---
_LOST_WORD = "дорозвід"
# "Чисто!" / "Поки чисто" — the same stand-down in shorthand (confirmed with the
# user after 07-18). Word-bounded so "чистота"/"очистити" never match; the rules
# gate also requires no district and no other-oblast scoping ("По Житомирщині
# чисто" is about Zhytomyr).
_STANDDOWN_CLEAN_RE = re.compile(r"(?<![а-яіїєґ])чисто(?![а-яіїєґ])")
# A stand-down whose next clause announces a live threat must close nothing —
# the live half wins. Curated adversatives, not bare "але" (too common in
# harmless asides). On 08-04 «Поки чисто. Але ще виходи!» closed 5 live tracks.
_STANDDOWN_LIVE_THREAT = ("паралельно", "але загроза", "але триває загроза",
                          "ще виходи", "ще можливі цілі", "можливі ще цілі")

# --- City-wide threat: aimed at the city as a whole, no raion ("Ціль на місто!",
# "Балістика на Київ"). During the sub-minute ballistic phase spotters warn the
# whole city before any raion is named, so this must raise a city alert rather
# than nothing. All three channels are Kyiv-dedicated, so a directional callout
# IS about Kyiv. STRONG phrases are the threat signal on their own; WEAK ones
# ("по Києву") also occur in news ("новини по Києву") and need a threat word. ---
_CITYWIDE_STRONG = ("на місто", "над містом", "на київ", "на столиц",
                    "увага місто", "увага, місто")
# Bare "Київ!!" — the city twin of a bare district callout, dropped 08-04 one
# second before "Балістика!!". Anchored to the WHOLE message: a loose "київ"
# stem would swallow every recap naming the city.
_CITYWIDE_BARE_RE = re.compile(r"^\W*(?:київ|столиця|столиці)\W*$")
# "над Києвом"/"над столицею" are WEAK, not strong, even though the twin "над
# містом" is strong: the corpus sweep found all three of their existing hits are
# «🌈 Над Києвом зʼявилася яскрава веселка» rainbow posts. With the threat-word
# gate, "4 БпЛА над Києвом" (raw 4824, which used to produce nothing at all)
# raises the city alert and the rainbows stay silent.
_CITYWIDE_WEAK = ("по місту", "по києву", "удар по києву", "по столиц",
                  "над києвом", "над столицею",
                  # City-BOUND phrasing from the same sweep: "до 10х ворожих
                  # БпЛА в бік Столиці", "~10х крилатих ракет в напрямку
                  # Столиці" — a live city warning that used to localize
                  # nowhere. Weak (needs a threat word) because "в напрямку
                  # Києва" also shows up in travel/logistics reposts.
                  "бік столиці", "бік києва", "напрямку столиці", "напрямку києва",
                  "напрямок києва", "напрямку на київ")
_THREAT_CONTEXT = ("ціль", "цілі", "ракет", "баліст", "шахед", "бпла", "дрон",
                   "загроз", "удар", "приліт", "вибух", "кинджал", "іскандер",
                   "каб", "с-400", "с400", "с-300", "с300", "циркон", "пуск")

# --- Threat-LEVEL bulletin: commentary about a target TYPE with no target and
# no place of its own ("Сьогодні червоний рівень по балістиці", "По балістиці
# тихо на даний момент"). The spotters run this as a standing side-channel
# beside the live callouts — 51 "по балістиці" messages in the captured corpus —
# and every one of them used to die silently after paying for an LLM call.
#
# Two shapes, mapped onto the notice kinds the feed already renders:
# RAISED -> `forecast` (the level is up / the warning still stands),
# QUIET  -> `status`   (nothing of that type is flying right now).
# RAISED is tested first, so a mixed "попередження дійсні, але поки тихо" reads
# as the warning rather than the lull.
#
# QUIET is emphatically NOT an all-clear: a spotter's "по балістиці тихо" must
# never close a track — the same reason _dispatch keeps a spotter's full відбій
# inert. It only states the situation in the feed. ---
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
# Oblast-scope situation reports ("По області 2-3 БПЛА", "В області цей один",
# "Залишився один в області"). The threat is in Kyiv OBLAST with no raion named:
# nothing to place on the map, but it answers the operator's actual question —
# is it near yet. `status`, not `forecast`; the "тривога в області" heads-up
# above is the forecast half of the same family.
_LEVEL_OBLAST = ("в області", "у області", "по області", "в обл.", "області вже",
                 "областi", "в київській області", "по київській області")

_LEVEL_QUIET = ("тихо", "не видно", "без запусків", "без пусків", "пусків немає",
                "наразі немає", "поки немає",
                "не фіксується", "спокійно", "ситуація спокійна", "минула без",
                "поки все спокійно", "фальш цілі", "фальшцілі",
                # The type-scoped all-quiet the spotters actually write when a
                # type stops being a problem: "По БПЛА в нас все чисто",
                # "Ніяких Кинджалів на даний момент немає". A NOTICE and never a
                # stand-down — the suppressor gate above keeps a real «чисто»
                # (lost_signal) on its own type-scoped path.
                "все чисто", "наразі чисто", "поки чисто", "момент немає",
                # The negative half of the launch/carrier families below. Both
                # say the word they are about ("без фіксації пусків", "ТУшки
                # неактивні", "Посадка 4× Ту-95МС на аеродром"), so without
                # these the forecast branches would read a stand-down as a
                # raised level — the exact inversion this list exists to stop.
                "без фіксац", "неактивн", "посадк")

# --- The two forecast families below are checked AFTER _LEVEL_QUIET on purpose.
# Both markers routinely sit in the same sentence as an all-quiet report
# ("Ситуація спокійна по балістиці. Чекатимемо відбою найближчим часом") and
# reading that as a raised level would be a lie in the operator's face. Quiet
# now wins; these speak only when nothing says quiet. ---
#
# A LAUNCH somewhere far away, with no place of ours to put on the map. This is
# the earliest warning a cruise wave gives — "Попередньо відбулися пуски зі
# стратегічної авіації" lands 30-90 min before anything reaches Kyiv, and it
# used to surface nowhere. The negative forms ("без пусків", "пусків немає") are
# already claimed by _LEVEL_QUIET above. The lookbehind keeps "Спуск!" (a live
# overhead callout, not a launch report) and "випуск" out.
_LEVEL_LAUNCH_RE = re.compile(r"(?<![а-яіїєґ])(?:за)?пуск(?:[иіауео]\w{0,3})?(?![а-яіїєґ])")
# ANTICIPATION of the next wave ("можлива повторна хвиля балістики", "ракети
# приблизно очікуємо 3-4 ранку", "поки ще діє балістична загроза"). A live
# callout never talks about "найближчим часом"; this is the sentence the
# operator plans the next hour around.
_LEVEL_AHEAD_RE = re.compile(
    r"найближчим часом"
    r"|можлив\w*\s+(?:\w+\s+)?(?:повторн|нов|чергов|наступн)"
    r"|(?:повторн|нов|чергов|наступн)\w*\s+хвил"
    r"|очікуєм|чекаєм"
    r"|варто реагувати"
    r"|ще діє"
)
# Carrier activity is its own notice family (_MISSILE_CARRIER, declared with the
# type keywords): pre-launch bookkeeping that is never a target on the map, and
# has nothing in it for the LLM to localize either.
#
# "Без змін" is the WEAK half of the quiet family, and it is weak because it
# usually modifies something else in the same sentence rather than being the
# news: "Без змін, найближчим часом очікуємо на виліт бомбардувальників" and "У
# повітрі без змін продовжують перебувати Ту-95МС" are both reports of carrier
# activity CONTINUING. So it is checked last, after the forecast families — it
# speaks only when nothing louder is in the message.
_LEVEL_QUIET_WEAK = ("без змін", "без критичних змін")
# "Quiet HERE, busy THERE" is the standard shape of a type bulletin: «По БПЛА в
# нас все чисто, ворог атакував частково Чернігівщину», «Біля Києва наразі
# чисто, ще одна група ракет на Черкащині». The foreign oblast is the contrast
# clause, not the subject — but `target_not_kyiv` (rightly, for a terse pulse)
# throws the whole message away over it. An explicit claim of OUR scope is what
# tells the two shapes apart.
_OWN_SCOPE_RE = re.compile(
    r"(?<![а-яіїєґ])[ву]\s+нас(?![а-яіїєґ])"
    r"|біля києва|по києву|[ву]\s+києві|для нашого регіону|нашого регіону"
)

# --- Retrospective attack SUMMARY ("Загалом по Києву пустили до 8 ракет") —
# recaps what already happened; info, never a live city alert. Distinguished from
# a live callout by an aggregate/past marker. "під час (нічної) атаки" is a
# retrospective frame. "завдав удару" + the official "повідомили у ПС"
# attribution mark the after-action ПС bulletin, which otherwise parsed as a
# fresh impact (it names a raion + "влучили"); a live strike is present-tense
# first-hand, never "завдав удару о 11:30 — повідомили у ПС".
#
# "попередньої атаки" / "було атакован" are the ANALYTIC past frame (raw 6145
# "…попередньої атаки, що була на Київ, ворог також застосував ракети ЗРК";
# raw 6143 "Місто було атаковане після атаки БПЛА"). They belong HERE, not in
# _RETROSPECTIVE with their synonyms, because the damage is a CITY-WIDE alert:
# "на київ" matched inside the past clause and raised a live ballistic threat
# over the whole city at 23:09 with nothing in the sky, while 6143 reached the
# LLM and was rescued into a live citywide notice. `summary` is what _citywide
# and should_fallback both exclude, so it fixes the alert and the paid call at
# once. Corpus (4242 unique): 3 hits for "попередньої атаки" (2 already
# summary), 1 for "було атакован" — nothing else changes behaviour.
#
# "застосував" was REJECTED here: 12 corpus hits that aren't already summaries,
# 3 of them unmatched messages that would newly become notices (a Zaporizhzhia
# strike report, two forecasts), and it buys nothing 6145 doesn't already get. ---
_SUMMARY = ("загалом", "всього", "за останні", "випустил", "під час",
            "завдав удар", "завдали удар", "завдано удар",
            "повідомили у пс", "повідомили у повітр",
            "попередньої атаки", "було атакован")

# Softer past-strike aggregate ("Близько 6 балістичних ракет ВДАРИЛО по Києву").
# Separate from _SUMMARY because "вдарил" also appears in a single live strike
# ("ракета вдарила по Троєщині"), so these count ONLY when no raion is named
# (rules.py::_summary's has_district gate). "застосован" (past passive) is the
# same register — raw 2167 raised a live citywide ballistic alert for an attack
# already over — and stays district-gated because its one district-bearing hit is
# a real localized impact. The present tense "застосовує" doesn't share the stem.
_SUMMARY_NO_DISTRICT = ("вдарил", "застосован")

# --- Every link-bearing message in the corpus is promo/donation/ad/meta, never a
# live callout — a spotter's sighting never carries a link. ---
_LINK_MARKERS = ("http", "t.me/")
# A bare 16-digit card number — the link-less donation variant. Same corpus
# guarantee. On 07-18 these slipped past _LINK_MARKERS and their "до останнього
# Шахеда та ракети" sign-off kept re-typing the channel context.
_CARD_NUMBER_RE = re.compile(r"(?<!\d)\d{16}(?!\d)")
# The link-less channel ad: a subscribe post listing localities ("❗️Вишневе
# тепер в Telegram… ▪️Вишневе ▪️Софіївська Борщагівка…" — raw 1038 raised 5
# raion tracks). Corpus: "тепер в telegram"/"якщо ти живеш у" hit only this ad;
# "підписуйс" also hits an already-suppressed power-schedule promo.
_AD_RECRUIT = ("тепер в telegram", "тепер у telegram", "якщо ти живеш у",
               "підписуйс", "підписуйтес")
# The link-less, card-less donation/engagement post — one channel runs these as
# a fundraiser scoreboard and audience call-and-response, and the sign-off
# ("бережіть себе", "до останнього шахеда") keeps them threat-flavoured. The
# identical "підтримало збір тільки 4ро людей" text appeared 8 times in one
# 5000-message window, each one paying for its own LLM call. Phrases are the
# scoreboard/engagement frames themselves, never the sign-off, so a real callout
# in the same register is untouched.
_ENGAGEMENT = ("підтримало збір", "підтримали збір", "підтримало тільки",
               "підтримала лише", "підтримав лише", "підтримало лише",
               "хто не пройде повз", "хто не ігнорує", "дайте реакцію",
               "дайте реакції", "дивитесь футбол", "буде зі мною", "люблю цілую")

# --- Decoy / EW ("Ймовірно, імітація", "працює РЕБ") — a modifier on the attack
# (attack.py::classify), NOT a replacement classification: a raid can be combined
# AND partly imitation. "реб" is 3 letters and collides, so it lives in
# _WHOLE_WORD like "каб". Behavioural inference ("every track vanished with no
# impacts" => decoy) is deliberately NOT done — a hint for a human, not a
# classifier signal. ---
_DECOY = ("імітаці", "реб", "обманк", "хибн", "фальшив")

# --- Hypersonic names — a flag on the attack (has_hypersonic), deliberately not
# a 6th target_type (which would spread into evals/icons/severity for one
# rendering need). "кинджал"/"аеробаліст" already type ballistic via _BALLISTIC;
# this list only ALSO raises the flag. ---
_HYPERSONIC = ("кинджал", "циркон", "аеробаліст")

# Case endings stripped (longest first) to reduce a word to a rough stem, so one
# regex matches most forms (Троєщина/Троєщині/Троєщину). The adjectival
# "-ськ/-цьк" root is deliberately KEPT (only "ий"/"ого"/"их" come off after it),
# so a raion adjective (Оболонський) stays distinct from the noun (Оболонь).
_SUFFIXES = ("ого", "ому", "ій", "ої", "ою", "их", "ий", "им", "ах", "ям",
             "ам", "ів", "ь", "и", "а", "я", "у", "ю", "і", "е", "о")

_APOSTROPHES = "'ʼ`’‘"

# Street-name collision guard: a raion adjective is also part of real street
# names ("Оболонський проспект", "Дарницьке шосе") in utility announcements.
# Same class as the Остер/"остерігайтеся" collision, fixed contextually instead
# of dropping the toponym: a district stem adjacent to one of these street nouns
# is a street, so DistrictMatcher discards it and keeps looking.
# "метро" is here for the same reason as the street words: Kyiv names metro
# stations after far-away cities, and the station is a Kyiv landmark, not the
# city it is named for. «район метро "Чернігівська"» is Дніпровський raion, not
# Чернігів 130 km north — the exact collision that kept "житомир"
# («станція метро "Житомирська"») out of the gazetteer for years.
_STREET_WORDS = ("проспект", "вулиц", "вул", "провулок", "бульвар", "узвіз", "шосе",
                  "набережн", "площ", "метро")

# Gazetteer entries that are a CITY sharing its name with an OBLAST. For these
# the adjectival form is the oblast, never the city — «мандрує Чернігівською»
# (область elided) is a direction, not a sighting over Чернігів. Kept as an
# explicit registry rather than a general "-ськ- in the tail" rule, because for
# most entries the adjective IS the place («Оболонський», «Білоцерківський»).
_OBLAST_CITY_STEMS = frozenset({"черніг"})

# Gazetteer aliases that must match as WHOLE words with no case tail — the same
# discipline rules.py::_WHOLE_WORD uses for "каб"/"реб", so a short alias can
# never fire inside an unrelated word. Two reasons to be in here: an alias below
# DistrictMatcher's 4-char stem floor (which would otherwise be dropped
# silently), or one whose stem collides with everyday words —
#   "пох"   -> "похолодання", "поховались", "походу"
#   "голос" -> "голосно", "проголосуйте", "оголосили"
#   "пущею" -> stems to "пуще", which fires inside "Пущено ракети"
#   "морі"  -> a prefix of "Морівськ", a real village on the northern corridor,
#              so «Район моря» swallowed it (all 10 real uses of море/моря/морі
#              in the corpus are the bare noun — "на море", "з моря")
#   "остер" -> fires inside "остерігайтеся"=beware. The town was left out of the
#              gazetteer for years because of it; as a whole word it is safe,
#              and it is the 3rd most-named place on the Chernihiv feed (16/300)
# Keep this set tiny: only forms the spotters really use as a standalone toponym.
#   "центр" -> a prefix of an adjectival family nobody means as the place
#              ("центральній", "центрального", "центрів") and of compounds
#              ("укргідрометцентр", "концентрацію", "децентралізацію"). As whole
#              words, "центр"/"центру"/"центрі" are 37 clean corpus hits and one
#              of the most-named places on the feed.
_WHOLE_WORD_ALIASES = frozenset({"чзв", "пох", "бц", "голос", "пущею",
                                 "море", "моря", "морі", "остер",
                                 "центр", "центру", "центрі",
                                 # The Antonov plant, next to Нивки. As a stem
                                 # it swallowed «Антоновичі» — a Chernihiv-oblast
                                 # village — and put a live target 150 km away on
                                 # a Kyiv microdistrict (raw 7249, 2026-08-21).
                                 # Both real case forms listed, like море/моря.
                                 "антонов", "антонова",
                                 # Both cities' power plant, as the spotters
                                 # type it bare. Three letters, so it could
                                 # never be a stem anyway; whole-word matching
                                 # also keeps it from eating "ТЕЦ-6" — that
                                 # entry explains 5 characters of the same word
                                 # and wins the specificity resolution in
                                 # DistrictMatcher.find. Swept over the corpus.
                                 "тец"})

# An alias that is also part of a PROPER NAME, keyed to the word that follows it.
# "Голос Києва" is a Telegram channel other channels quote ("Голос Києва —
# @golos_kieva попередив про загрозу"), not a callout over Holosiivskyi. Same
# idea as _FOREIGN_SEA_ADJ in matcher.py: the toponym stays, its collision is
# resolved by the adjacent word.
_ALIAS_NEXT_WORD_VETO: dict[str, tuple[str, ...]] = {
    "голос": ("києва", "кієва"),
    # An institution's name, not the middle of the city: «Центр спеціальних
    # операцій "Альфа" СБУ», «керівниця центру міжнародної...», «центр
    # досліджень». Swept the whole corpus for what follows a standalone
    # "центр": the place is followed by nothing, an emoji, "Києва", "міста",
    # "увага", "уважно", "знову", "летить" — an organisation, by a genitive
    # qualifier. These three are all of them that occur.
    "центр": ("спеціальн", "міжнародн", "дослідж"),
    "центру": ("спеціальн", "міжнародн", "дослідж"),
    "центрі": ("спеціальн", "міжнародн", "дослідж"),
}

# The mirror image: an alias that only counts when the PRECEDING word starts
# with one of these. "церкв" is Біла Церква's only matchable word (a spaced name
# never becomes one stem), but on its own it would read a real strike report
# ("приліт у церкву") as a callout over a town 80 km south.
_ALIAS_PREV_WORD_REQUIRED: dict[str, tuple[str, ...]] = {"церкв": ("біл",)}

# --- Everything above, as one word-start stem set ---
# Consumed by `toponyms.py` to answer "is this word already something the parser
# knows about?" — a word the vocabulary explains is never a missing gazetteer
# entry. Assembled here rather than re-listed there so a stem added above is
# automatically excluded from the coverage-gap queue too; the queue silently
# re-proposing "реактивних" as a place after someone extends _JET is exactly
# the drift this avoids.
#
# Multi-word phrases are kept out: these are matched against single tokens, so a
# phrase could never match, and leaving them in would only be misleading.
NON_TOPONYM_STEMS: frozenset[str] = frozenset(
    stem
    for stem in (
        *_BALLISTIC, *_MISSILE, *_JET, *_JET_MODEL, *_SHAHED,
        *_CLEAR, *_DESTROYED, *_UNCONFIRMED, *_CONFIRMED, _UNSCOPED_CLEAR_WORD,
        *_NEW_TARGET, *_MOVEMENT_CUE, *_PULSE_WORD,
        *_THREAT_CONTEXT, *_AFTERMATH, *_CIVIC_NOTICE, *_REPORTAGE,
        *_IMPACT, *_POWER_OUTAGE, _SIREN_WORD, _LOST_WORD, _DAY_RECAP_WORD,
    )
    if " " not in stem
)

# The numerals are the same vocabulary but must be matched as WHOLE words, never
# as prefixes — which is how the parser itself uses them (`_NUM` carries a
# word-start guard and every caller anchors the end). Ukrainian place names
# begin with them often enough that treating them as stems is a live hazard:
# "три" is the head of Трипілля, "троє" of Троєщина, "семи" of Семиполки.
NON_TOPONYM_WORDS: frozenset[str] = frozenset(_NUM_WORDS)

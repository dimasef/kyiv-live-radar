"""Curated Ukrainian keyword/phrase vocabulary and regex literals for the rule
parser (see `rules.py`). Pure data — no matching/decision logic here.
"""

from __future__ import annotations

import re

# --- Target type keywords (checked in priority order) ---
# Ballistic / aeroballistic — checked FIRST: the most time-critical class
# (seconds of flight) and it must win over the generic "ракет" match in the
# same message ("балістична ракета" -> ballistic, not missile). Kept a DISTINCT
# type from cruise/generic "missile" because the two drive different behavior:
# a ballistic is sub-minute and un-spottable over a specific raion, so it's a
# CITY-WIDE, no-trajectory threat; a cruise missile flies a route spotters
# track district-to-district, so it draws a real vector. С-300/400 are launched
# in a ballistic (surface-to-surface) mode against cities — spotters call them
# балістика, so their designations belong here too. "Циркон" (hypersonic
# cruise) flies the same sub-minute, un-spottable profile and spotters mix it
# freely into the ballistic callouts ("Балістика і циркони") — during the
# 07-18 mass attack a channel that mostly said "циркони" never refreshed its
# type context and produced a night of "unknown" tracks, so it types here too
# (the hypersonic INCIDENT flag stays separate, see _HYPERSONIC).
_BALLISTIC = ("баліст", "іскандер", "кинджал", "с-400", "с400", "с-300", "с300",
              "аеробаліст", "циркон", "гіперзвук")
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
                       "очікуватимемо на відбій", "очікується відбій",
                       # infinitive + genitive ("відбою") forms: "будемо
                       # очікувати на відбій", "чекатимемо відбою" — waiting FOR
                       # the all-clear, not announcing one.
                       "очікувати на відбій", "очікувати відбій", "очікувати відбою",
                       "чекати відбій", "чекати на відбій", "чекати відбою",
                       "чекаємо відбою", "чекатимемо відбою", "очікуємо відбою",
                       "очікуватимемо відбою", "очікується відбою",
                       "коли відбій", "коли вже відбій",
                       # "скоріш за все скоро відбій" — PREDICTS the all-clear,
                       # doesn't announce one; a real clear says "Дали відбій"/
                       # "Відбій тривоги", never "скоро/надія на відбій" (swept).
                       "скоро відбій", "надія на відбій")
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
# it corroborates the alert and bumps the stated count. "вихід" = a launch/exit
# callout in this feed.
_PULSE_WORD = ("ціль", "цілі", "вихід", "ракет", "баліст", "шахед", "бпла", "дрон",
               "циркон",
               # 07-18 additions — the words the spotters actually shouted
               # between toponyms while everything above stayed silent:
               "цілей",   # genitive ("Декілька цілей", "До 6 цілей!") — "ціль"/"цілі" don't substring-match it
               "пуск",    # "Ще пуски!" — same meaning as "вихід"
               "пада",    # "Падають!", "2 падають!!!!" — live incoming confirmation
               "летить", "летять")  # "2 штуки летить", "Ще летить"

# --- Movement-frame cues: words that mark a multi-district message as ONE
# target moving along a route ("Проходять Чернігівщину… через Броварський
# район", "курсом на Троєщину") rather than an enumeration of simultaneous
# separate targets ("Вишневе Жуляни", "Троя,Оболонь увага!"). On 07-18 every
# enumeration glued all its districts onto ONE track, recreating the zigzag
# mega-track (and a corroboration cascade onto the wrong track). ---
_MOVEMENT_CUE = ("курс", "у бік", "в бік", "через", "прямує", "рухаєт", "повз",
                 "напрям", "заходить", "захід у", "летить на")
# A district inside a prepositional phrase is a located/directed frame, not a
# bare enumeration item ("удар по Оболоні", "над Оболонню", "з Броварів").
_PREPOSITION_BEFORE_DISTRICT = ("на", "у", "в", "до", "з", "зі", "із", "над",
                                "біля", "під", "по")

# --- Aftermath / consequence vocabulary. A message describing the RESULT of a
# strike (casualties, damage, rescue) is NEWS about a place, not a live target
# to track — even if it names a district. These suppress a sighting. ---
_AFTERMATH = ("постраждал", "загинул", "поранен", "жертв", "уламк", "пошкодж",
              "зруйнов", "врятув", "рятувальник", "надзвичайник", "дснс",
              "багатоповерхів", "наслідк", "кмва", "госпіталіз", "медик",
              "евакуй", "загибл", "потерпіл",
              "пожеж",       # "пожежі на Трої" — fire footage is aftermath, not a sighting
              # Burning verb (post-strike fire) — "горять автомобілі", "вигорілі
              # авто", "горять офіси/склади". A district-bearing strike report
              # that ALSO states an impact keyword stays a real impact (the
              # aftermath carve-out `and not impact`). Stems chosen to avoid
              # collisions: "горіл"/"згорі" ⊄ "Вишгород"; "горять" ⊄ "говорять".
              "горить", "горять", "горіл", "згорі",
              # "палає/палають" — same post-strike-fire verb the "гор-" stems
              # cover ("Вся Лукʼянівка палає.." raised a live ballistic track on
              # 07-19). Full forms, NOT the bare stem "пала": "впала" (ракета
              # впала) contains it and must keep its live meaning.
              "палає", "палають", "палала", "палало",
              "відновленн")  # "виділить... на відновлення" — reconstruction-funding news

# --- Air-defence action vocabulary. "Відпрацювали установки по Дарницькому та
# Соломʼянському", "працює ППО" — a report that OUR air defence engaged over some
# districts. It's not an incoming target and not a trajectory: matching its two
# named districts would draw a bogus target-vector between them. Suppress it like
# aftermath (an impact keyword in the same message still wins — real strike). ---
_AD_ACTION = ("відпрацюв",   # відпрацювали/відпрацювала/відпрацьовує (установки/по цілі)
              "працює ппо", "ппо працює", "працює наша ппо", "сили ппо", "робота ппо")

# --- Civic / municipal notices: public-transport route & schedule changes and
# road-traffic reorganizations that the spotter channels reprint ("тимчасово
# змінять маршрути тролейбусів", "обмежать рух транспорту", "зачинять фунікулер
# на ремонт"). These name streets/neighbourhoods a gazetteer entry can match
# (e.g. "Мінського масиву") but are pure city news, never a live target — the
# T217/M668 false-positive class. Suppressed like aftermath, and only ever on a
# type-unknown message (a named shahed/missile/ballistic is never a bus notice),
# so a real target that merely passes over a road can't be silenced. Every stem
# below is transport/traffic-specific — validated absent from real sightings in
# the captured corpus. NB: bare "маршрут"/"рух"/"транспорт" are intentionally
# NOT here — a real target "змінила маршрут руху"; only the transport-mode words
# and multiword traffic phrases are safe. ---
_CIVIC_NOTICE = ("тролейбус", "трамвай", "маршрутк", "фунікулер", "автобус",
                 "громадського транспорт", "громадський транспорт",
                 "дорожнього руху", "рух транспорт", "руху транспорт",
                 "організації руху", "обмежать рух", "обмежуватимуть рух",
                 "перекрито рух", "перекрито середню")

# єППО — the crowd/sensor air-alert app. Spotters RELAY its marks but routinely
# DISMISS them as unverified ("локаційно не видно, відмітки єППО Вишневе, Макарів,
# ...") — app marks, not confirmed targets. Suppress only when the message pairs
# an єППО mention with a "we don't see it / dorozvidka / false" cue (see
# rules._eppo_marks), so a genuine "єППО показує ціль на Троєщині, підтверджую"
# is never silenced. _EPPO_WORD covers the Cyrillic-є spelling and the common
# Cyrillic-е typo.
_EPPO_WORD = ("єппо", "еппо")
_EPPO_DISMISS = ("не видно", "не бачим", "не фіксу", "не спостеріга", "дорозвідк",
                 "хибн", "локаційно чист")

# --- Impact / strike-location vocabulary. A LOCALIZED hit ("влучання по будівлі
# в Дніпровському районі", "пошкоджено будівлю у Святошинському") is a confirmed
# strike whose LOCATION is worth putting on the map — distinct from generic
# aftermath news (casualties/rescue/funding) that we suppress. Requires a
# district: without one ("є влучання десь") there is nothing to place. When both
# an impact verb AND aftermath words are present (a strike report that also
# mentions casualties), the impact reading WINS — the location is the useful
# signal. "пошкодж"/"зруйнов" also live in _AFTERMATH so a district-less "damaged
# a building" still suppresses; only WITH a district do they become an impact. ---
# "влучил" covers the verb forms (влучила/влучило/влучили) — on 07-18 Кличко's
# "Балістика влучила прямо в багатоповерхівку у Шевченківському районі" carried
# no noun form, so the aftermath stem "багатоповерхів" won and a real strike on
# a residential building never reached the map.
_IMPACT = ("влучанн", "влучил", "приліт", "пошкодж", "зруйнов")

# Retrospective footage/report of a PAST strike ("На відео наслідки останньої
# атаки", "наслідки нічної атаки") — NOT a fresh hit to place on the live map. A
# genuine strike report ("влучання в Дніпровському районі") never frames itself
# as "останньої/минулої атаки" or "на відео". Blocks the impact reading so the
# message falls back to plain aftermath suppression (no live marker, no incident,
# no "attack" banner). ---
_RETROSPECTIVE = ("на відео", "останньої атаки", "минулої атаки", "нічної атаки",
                  "вчорашн", "минулої ночі")

# --- Power-grid / utility-outage vocabulary. A blackout notice ("тимчасово
# немає світла через аварійне пошкодження, енергетики відновлюють
# електропостачання") names districts and says "пошкодж" — but that's grid
# damage, not a missile strike. Without it, `_impact` reads the outage as a
# confirmed hit (пошкодж + district) and pins a phantom impact marker. Blocks
# the impact reading UNLESS an unambiguous strike word (влучанн/приліт) is also
# present, so a real "внаслідок влучання знеструмлено підстанцію" still counts.
# Stems are grid-specific (not bare "світл") to avoid eating genuine building
# strikes that merely mention lights. ---
_POWER_OUTAGE = ("електропостачанн", "електроенерг", "електромереж", "енергетик",
                 "енергооб", "знеструмл", "підстанці", "обленерго", "дтек",
                 "аварійне пошкодж", "немає світл", "нема світл", "без світл",
                 "зникло світл", "відключенн світл")

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

# --- Preparatory/forecast advisory ("Росія готує удар балістикою С-400 по
# Києву в цю та наступну добу", "РФ готується до масштабної атаки") — the
# enemy is PREPARING/PLANNING a future strike, not one currently in flight or
# detected. Same treatment as the "якщо"/"у разі" hedges above: a forecast,
# not a live sighting.
#
# Swept the full corpus (871-message jsonl + live DB, 1087 raw messages):
# - "готу" is a SAFE bare stem (готує/готується/готують/готуватися) gated on
#   a co-occurring weapon word (_THREAT_CONTEXT, same gate _citywide already
#   uses for "по києву") — every real hit is a forecast/situational-report
#   bulletin ("Вечірній звіт...", "Є ймовірність, що на вечір готує
#   балістичний удар"), no live-sighting collision found. A genuine live
#   spotter shorthand using "готується" WITHOUT a weapon word ("Заходить
#   перший в район Жукин, готується знову Троя") correctly falls outside the
#   gate and keeps its district.
# - "план" is NOT safe as a bare stem, even gated on a weapon word: "Кияни,
#   плануйте день з урахуванням тривог! Зараз знову реактивні «Шахеди»...
#   намагаються прорватися в бік Києва" pairs the reader-facing imperative
#   "плануйте" (plan YOUR day) with a real live weapon word two clauses
#   later — bare-stem+weapon-word would wrongly suppress that live shahed
#   notice. Anchored to 3rd-person "планує"/"планують" instead, which only
#   ever describes the enemy's plan, never the reader's.
# "ворог може застосувати до 100 ракет…", "рашисти можуть застосувати крилаті
# Іскандери" — a MAY-deploy forecast, same register as готує/планує. The full
# два-слівні phrases (not a bare "застосув") avoid colliding with the live
# nominal "загроза застосування балістики". Corpus-swept: the only currently-
# kept hit is the 24h forecast bulletin this catches; no live sighting uses it.
_FORECAST_VERB = ("готу", "планує", "планують", "може застосув", "можуть застосув")

# --- Night/evening-timeframe threat forecast ("На сьогоднішню ніч по Києву/
# області — загроза по балістичному озброєнню актуальна!", "Загроза по
# балістиці на цю ніч теж актуальна", "На ніч знову червоний рівень по
# балістиці") — a heads-up about a COMING night, not a target in flight; the
# «по Києву» inside made one raise a live citywide ballistic alert (raw 1771,
# 2026-07-18). No verb to anchor on (the register is nominal: «загроза ...
# актуальна/підвищена/залишається»), so the anchor is the explicit timeframe
# phrase, gated on a co-occurring weapon word like _FORECAST_VERB above.
# Swept the full corpus (871 jsonl + 1776 live raw): ~10 hits, ALL of them
# forecast bulletins; no live sighting uses these phrases («вночі» was
# considered and rejected — too broad, collides with aftermath recaps that
# have their own filter). Clear/destroyed/impact carve-outs in _negated keep a
# real «Відбій ... цієї ночі ...» recap safe.
_FORECAST_TIMEFRAME = ("на сьогоднішню ніч", "на цю ніч", "цієї ночі", "на ніч",
                       "протягом ночі", "на вечір", "найближчими ноч")

# --- "можуть бути"/"може бути" as a bare hedge is UNSAFE alone: a real
# confirmed-strike report with real casualties across 4 real districts uses
# the same words for an unrelated rescue-uncertainty clause ("...частково
# зруйнований житловий будинок, під завалами можуть бути люди...") — a bare
# phrase match would wipe that correct impact marker. Anchored instead to an
# explosion/strike noun immediately following, matching the actual forecast
# register ("Знову можуть бути вибухи до тривоги") without touching "можуть
# бути люди/постраждалі".
_HEDGE_MODAL_RE = re.compile(r"(?:можуть бути|може бути)\s+(вибух|обстріл|удар|приліт|пуск)")

# --- Advisory / relayed-opinion PREVIEW of which raions MIGHT be hit — a
# second-hand or forecast bulletin, not a first-hand live sighting. Three
# real shapes seen in the feed (all 07-23, «Віраж Києва»):
#   - relayed rumour:     «Пишуть що також є загроза для Броварів»
#   - relayed speculation:«По тому що я читав в інших джерелах … ймовірно
#                          ворога цікавлять такі райони: …» + a raion list
#   - warning bulletin:   «Є попередження про використання 35 балістичних
#                          ракет … Підвищена загроза таким районам: …»
# Each listed a set of gazetteer raions and so raised live tracks/dots for
# targets not in flight. Folded into the conditional-hedge path (-> _negated),
# same family as the «якщо»/«готує»/forecast-timeframe hedges above: the
# message is about a POSSIBLE / SECOND-HAND threat, not a live callout, and
# gets the same clear/destroyed/impact carve-out.
#
# _ADVISORY_RELAY phrases are self-sufficient — the relay/warning register
# alone marks the class (corpus-swept: 871 jsonl + 1776 live raw, these
# multiword phrases appear ONLY in this class, zero live-sighting collision).
# The nominal «підвищена загроза» advisory and the «ворога цікавлять» /
# «найближчими ночами» forecast markers are handled in rules._has_conditional_hedge
# with a co-occurring weapon word (_THREAT_CONTEXT), same gate as the forecast
# verb/timeframe rows — «підвищена загроза» alone also appears in an unrelated
# air-pollution notice («…відповідає підвищеній загрозі») that carries no
# weapon word and must stay untouched.
# "За даними моніторів, ворог може застосувати…", "За даними розвідки, в
# найближчі 48 годин…" — a relayed-source forecast bulletin. Corpus-swept
# (2562 unique): 5 hits, all news/recap/forecast (aftermath "за даними медиків",
# a ПС shoot-down recap, two forecast bulletins) — zero first-hand spotter
# callouts ("за даними" is the register of a monitor relaying, never a live
# sighting), so it carries the class on its own like the phrases above.
_ADVISORY_RELAY = ("пишуть що", "пишуть, що", "інших джерелах", "є попередження про",
                   "за даними")

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

# --- Spotter buzz-slang: "бджілки"/"бджоли" (bees) = OUR drones over enemy
# territory, so a message about them is reassurance chatter, never an incoming
# threat to Kyiv or a precise live callout. Corpus-swept (871 jsonl + live raw,
# 2508 unique): all 3 hits are commentary ("там наші бджілки. До відбою уважно",
# "добрі бджоли шуму наводять", "Кажу одразу, що там реактивні бджілки, але до
# відбою уважно"). The last one carries
# "реактивні" (a jet keyword), so it typed the channel context as jet_drone and
# a citywide ballistic callout ("На Київщину!") 26s later INHERITED it — the
# main city card of the 07-24 ballistic salvo stuck at «БпЛА» (jet_drone never
# upgrades to the missile family). So a buzz-slang message must not set/consume
# the per-channel live type context — see ingest._note_and_inherit_type. ---
_BUZZ_CHATTER = ("бджілк", "бджол")

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
# "Чисто!" / "Поки чисто" — spotter shorthand for the SAME stand-down
# (confirmed with the user after 07-18: «чисто» = дорозвідка, targets not
# currently seen). Word-bounded so "чистота"/"очистити" never match; the
# rules-level gate additionally requires no district AND no other-oblast
# scoping ("По Житомирщині чисто" is about Zhytomyr, not a Kyiv stand-down).
_STANDDOWN_CLEAN_RE = re.compile(r"(?<![а-яіїєґ])чисто(?![а-яіїєґ])")
# A stand-down message that ALSO announces a live, continuing threat clause
# («Дорозвідка триває, але паралельно триває загроза балістики з Брянщини…»)
# must NOT close everything — the live half wins (raises the directional axis).
# Curated adversative markers, not bare "але" (too common in harmless asides).
_STANDDOWN_LIVE_THREAT = ("паралельно", "але загроза", "але триває загроза")

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
                   "каб", "с-400", "с400", "с-300", "с300", "циркон", "пуск")

# --- Retrospective attack SUMMARY, not a live target ("Загалом по Києву пустили
# до 8 ракет", "Росія випустила близько 8 балістичних С-400 за останні 15
# хвилин"). These recap what ALREADY happened (aggregate count, past frame) —
# useful info, but NOT a live threat to raise a city alert for. Distinguished
# from a live callout ("3 ракети", "ціль на місто") by an aggregate/past marker.
# Curated word list, same shape as _AFTERMATH. "під час (нічної) атаки" is a
# retrospective FRAME — an after-the-fact report ("Під час нічної атаки на Київ
# запустили 6 балістичних… — ПС"), not a live callout. ---
_SUMMARY = ("загалом", "всього", "за останні", "випустил", "під час")

# Softer past-strike aggregate marker ("Близько 6 балістичних ракет ВДАРИЛО по
# Києву", "всі 30 балістичних… вдарили по будинках") — a recap of what already
# hit. Kept SEPARATE from _SUMMARY because "вдарил" also appears in a single
# live strike ("ракета вдарила по Троєщині"), so it counts as a summary ONLY
# when NO raion is named (see rules.py::_summary's has_district gate) — an
# aggregate citywide recap, not a district impact to map.
#
# "застосован" (past passive: застосовано/застосовані) is the same aggregate-
# recap register ("Ймовірно найбільша балістична атака… Було застосовано
# близько 40 ракет" — raw 2167 raised a live citywide ballistic alert for an
# attack that had ALREADY happened). Kept district-gated like "вдарил": the one
# district-bearing corpus hit ("ракета потрапила… на Подолі… летіли Циркони")
# is a real localized impact and must stay. The present tense "застосовує" (a
# live "ворог застосовує Шахеди") does NOT share this stem, so only the
# retrospective participle matches.
_SUMMARY_NO_DISTRICT = ("вдарил", "застосован")

# --- URL / link presence. Every link-bearing message in the real corpus is
# promo / donation / channel-boost / ad / meta ("створив ракетний канал…
# https://t.me/…", "добити 9 рівень в каналі", "фальш ціль — пояснення"), NEVER
# a live target callout — a spotter's sighting never carries a link. So a URL is
# a safe suppression signal (see rules.py::_promo), with the same clear/
# destroyed/impact carve-out as _aftermath. ---
_LINK_MARKERS = ("http", "t.me/")
# A bare payment-card number ("Моно - 4441111126308174") — the link-less donation
# post variant. Same corpus guarantee as links: no real target callout carries 16
# contiguous digits. On 07-18 these posts slipped past _LINK_MARKERS and their
# "до останнього Шахеда та ракети" sign-off kept re-typing the channel context.
_CARD_NUMBER_RE = re.compile(r"(?<!\d)\d{16}(?!\d)")
# The LINK-LESS channel-ad variant: a recruitment/subscribe post that carries
# no URL but lists localities to pull in subscribers ("❗️Вишневе тепер в
# Telegram\nЯкщо ти живеш у такому населеному пункті:\n▪️Вишневе ▪️Софіївська
# Борщагівка …" — raw 1038 raised 5 raion tracks). The URL premise of
# _LINK_MARKERS doesn't cover it, so anchor on the recruitment register
# instead. Corpus-swept (871 jsonl + 1776 live raw): "тепер в telegram" /
# "якщо ти живеш у" hit ONLY this ad; "підписуйс" additionally hits a
# power-schedule channel promo (already suppressed) — no live-sighting
# collision. Same clear/destroyed/impact carve-out as the link/card variants.
_AD_RECRUIT = ("тепер в telegram", "тепер у telegram", "якщо ти живеш у",
               "підписуйс", "підписуйтес")

# --- Decoy / electronic-warfare vocabulary ("Ймовірно, імітація", "працює
# РЕБ", "хибна ціль") — a modifier on the attack (see app/domain/attack.py::
# classify: decoy_suspected), NOT a replacement classification: a raid can be
# combined AND partially imitation. Curated list per the domain-model-v2 plan,
# same shape as _AFTERMATH/_NEGATION. "реб" is a 3-letter abbreviation that
# would otherwise collide with common words, so it goes in _WHOLE_WORD (same
# treatment as "каб"). Behavioral inference ("every track vanished with no
# impacts" => decoy) is explicitly NOT done here — that's a hint at most, left
# to a human reading the incident, not a classifier signal. ---
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
_STREET_WORDS = ("проспект", "вулиц", "вул", "провулок", "бульвар", "узвіз", "шосе",
                  "набережн", "площ")

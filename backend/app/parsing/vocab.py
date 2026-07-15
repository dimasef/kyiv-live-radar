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
_PULSE_WORD = ("ціль", "цілі", "вихід", "ракет", "баліст", "шахед", "бпла", "дрон")

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
_FORECAST_VERB = ("готу", "планує", "планують")

# --- "можуть бути"/"може бути" as a bare hedge is UNSAFE alone: a real
# confirmed-strike report with real casualties across 4 real districts uses
# the same words for an unrelated rescue-uncertainty clause ("...частково
# зруйнований житловий будинок, під завалами можуть бути люди...") — a bare
# phrase match would wipe that correct impact marker. Anchored instead to an
# explosion/strike noun immediately following, matching the actual forecast
# register ("Знову можуть бути вибухи до тривоги") without touching "можуть
# бути люди/постраждалі".
_HEDGE_MODAL_RE = re.compile(r"(?:можуть бути|може бути)\s+(вибух|обстріл|удар|приліт|пуск)")

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

# Softer past-strike aggregate marker ("Близько 6 балістичних ракет ВДАРИЛО по
# Києву", "всі 30 балістичних… вдарили по будинках") — a recap of what already
# hit. Kept SEPARATE from _SUMMARY because "вдарил" also appears in a single
# live strike ("ракета вдарила по Троєщині"), so it counts as a summary ONLY
# when NO raion is named (see rules.py::_summary's has_district gate) — an
# aggregate citywide recap, not a district impact to map.
_SUMMARY_NO_DISTRICT = ("вдарил",)

# --- URL / link presence. Every link-bearing message in the real corpus is
# promo / donation / channel-boost / ad / meta ("створив ракетний канал…
# https://t.me/…", "добити 9 рівень в каналі", "фальш ціль — пояснення"), NEVER
# a live target callout — a spotter's sighting never carries a link. So a URL is
# a safe suppression signal (see rules.py::_promo), with the same clear/
# destroyed/impact carve-out as _aftermath. ---
_LINK_MARKERS = ("http", "t.me/")

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
_STREET_WORDS = ("проспект", "вулиц", "провулок", "бульвар", "узвіз", "шосе",
                  "набережн", "площ")

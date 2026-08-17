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
# Cruise/guided-bomb/generic. Bare "ракет" is ambiguous and defaults here; only
# an explicit ballistic marker above promotes it.
_MISSILE = ("ракет", "крилат", "калібр", "х-101", "х-59", "х-22",
            "каб", "авіабомб", "керован авіа")
# Bare "реактив", not "реактивн" — the noun form is used too ("3 реактива повз
# Славутич"); on 08-04 those stayed unknown and inherited ballistic.
_JET = ("реактив", "швидкісн")
_SHAHED = ("шахед", "shahed", "мопед", "герань", "герані", "дрон", "бпла",
           "безпілотник", "безпілотн")

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

# --- New-target markers (start a fresh track) ---
_NEW_TARGET = ("новий", "нова ціль", "ще один", "ще одна", "інша ціль",
               "друга ціль", "додатков", "нові цілі")
# "ще N <noun>" — additional targets. Noun-anchored, not bare "ще \d+", so a
# time reference ("ще 20хв") never matches.
_NEW_TARGET_COUNT_RE = re.compile(
    r"ще\s+\d+\s+(?:ракет|ціл|шахед|бпла|дрон|баліст)", re.IGNORECASE
)

# Count shorthand: a number then х/x ("2х", "їх вже 3х"). The lookahead drops
# "20хв" and numbers glued to words. This is the size of ONE group flying
# together — it annotates the track, it never fabricates N tracks.
_COUNT_RE = re.compile(r"(\d+)\s*[хx](?![а-яіїєґa-z])", re.IGNORECASE)
# A number directly qualifying a target noun ("3 ракети", "2 цілі").
_COUNT_NOUN_RE = re.compile(r"(\d+)\s+(?:ракет|ціл|шахед|бпла|дрон|баліст)", re.IGNORECASE)

# Terse target/launch "pulse" with no location ("Ціль!", "Ще вихід", "3 ракети").
# Too terse to localize alone; only acted on during an open city-wide alert.
# "вихід" = a launch callout here. The 07-18 additions are the words spotters
# actually shouted between toponyms while everything above stayed silent.
_PULSE_WORD = ("ціль", "цілі", "вихід", "ракет", "баліст", "шахед", "бпла", "дрон",
               "циркон",
               "цілей",   # genitive — "ціль"/"цілі" don't substring-match it
               "пуск",    # "Ще пуски!"
               "пада",    # "Падають!" — live incoming
               "летить", "летять")

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
                 "перекрито рух", "перекрито середню")

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
_CITYWIDE_WEAK = ("по місту", "по києву", "удар по києву", "по столиц")
_THREAT_CONTEXT = ("ціль", "цілі", "ракет", "баліст", "шахед", "бпла", "дрон",
                   "загроз", "удар", "приліт", "вибух", "кинджал", "іскандер",
                   "каб", "с-400", "с400", "с-300", "с300", "циркон", "пуск")

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
_STREET_WORDS = ("проспект", "вулиц", "вул", "провулок", "бульвар", "узвіз", "шосе",
                  "набережн", "площ")

# Gazetteer aliases shorter than DistrictMatcher's 4-char stem floor, which
# would otherwise drop them silently. Matched as WHOLE words with no case tail —
# the same discipline rules.py::_WHOLE_WORD uses for "каб"/"реб" — so a 3-letter
# alias can never fire inside an unrelated word. Keep this set tiny: only
# abbreviations the spotters actually use as a standalone toponym.
_WHOLE_WORD_ALIASES = frozenset({"чзв"})

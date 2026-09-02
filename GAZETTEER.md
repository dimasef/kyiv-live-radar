# GAZETTEER.md — how `app/gazetteer.py` works and how to grow it

The gazetteer is the single biggest lever on parser accuracy — well ahead of the
LLM. It is also the easiest place to introduce a silent, hard-to-see bug: a bad
entry does not crash, it puts a target on the wrong side of the country.

This file holds the reasoning that used to live as comments inside
`app/gazetteer.py`. The module itself now keeps only the notes you need while
editing a specific line. Read this before adding, changing or removing an entry.

## Contents

- [Entry shape](#entry-shape)
- [What the matcher does to a name](#what-the-matcher-does-to-a-name)
- [Adding an entry: the procedure](#adding-an-entry-the-procedure)
- [The failure classes](#the-failure-classes)
- [Names deliberately NOT added](#names-deliberately-not-added)
- [Entries kept under watch](#entries-kept-under-watch)
- [How the list grew](#how-the-list-grew)

---

## Entry shape

```python
{"name_uk": "Ріпки", "name_en": "Ripky", "lat": 51.8036, "lon": 31.0931,
 "region": "chernihiv", "aliases": ["ріпок"]}
```

| Field | Meaning |
|---|---|
| `name_uk` | Display label. Also the source of the primary stem. |
| `name_en` | **The upsert key** — `seed.py` matches rows on this, not on `name_uk`. Two entries sharing it silently overwrite each other; that is why homonyms carry a suffix (`VyshneveCH`, `DniprovskeCH`, `LebedivkaCH`). |
| `lat` / `lon` | One representative point per area (approximate centroid). Enough for a marker and a coarse vector; not a polygon. |
| `aliases` | Spelling variants, abbreviations and inflections the spotters actually type. Matched case-insensitively after normalization. |
| `region` | Optional, defaults to `kyiv`. Decides which **track pool** a sighting joins and which region the event feed files it under, so it must follow real geography — not "which channel usually reports it". Славутич is administratively Kyiv oblast but sits 150 km north, so it is `chernihiv`. |
| `region_only` | Optional. Makes the entry matchable **only** by a channel reporting from its own region — `DistrictMatcher` drops it from every other region's index entirely. |
| `match_context` | Optional. This entry's OWN neighbouring-word rules, for a word it shares with another entry. See "Two entries, one word" below. |

An entry that is itself a street or a square (its `name_uk` contains one of
`vocab._STREET_WORDS`) is exempt from `_is_street_reference`. Without that,
«Проспект Перемоги» was vetoed by the very word it is named after — the guard
that keeps «Оболонський проспект» off Оболонь fired on the one phrasing the
entry exists for. The same guard also stops at a comma now: «Суми, Проспект
Перемоги» is two callouts, not a street reference. Quote marks are NOT a stop —
they wrap a name («метро «Бориспільська»»), which is what `_EDGE` is for.

`CITYWIDE_NAME_EN` marks the sentinel "Київ" entry at the end of the list: a
city-wide threat («ціль на місто») has to attach its event to *some* district
row. `DistrictMatcher` skips it, and the LLM never sees it — otherwise it would
over-match every "у Києві…". Detection is the parser's `citywide` flag.

### `region` vs `region_only`

`region` alone is a label plus a tie-break: `DistrictMatcher(prefer_region=…)`
uses it only to break a tie between two entries that explain the *same amount*
of a word. A lone entry faces no tie, so `region` cannot stop a Kyiv channel
from matching a northern village.

`region_only` is the hard version, for a name both oblasts genuinely share as a
**local** landmark — «ТЕЦ», «вокзал», «летовище», «Кільцева», or village names
as common as Іванівка / Новоселівка / Олександрівка / Залісся / Піски / Буда /
Дачне / Брусилів. Hidden from the other region's matcher, those messages simply
stay unmatched — which is where they were anyway.

---

## What the matcher does to a name

Everything below is why entries look the way they do. Source:
`app/parsing/matcher.py`.

**Stemming strips case endings only.** `_stem()` removes a known suffix but
never cuts below 4 characters. It cannot bridge a vowel or consonant change
*inside* the root, which is where most aliases come from:

- «Ріпки» → stem `ріпк`, but the genitive plural is «ріпок» (и drops, о appears
  inside the root) → alias.
- «Пирогівці» / «пироговці», «Голінка» / «Голинка» — і↔о and і↔и alternations.
- «Бишів» → `бишів`, but oblique cases are Бишева/Бишеві → aliases.

**Four-letter names keep their nominative.** The stemmer will not cut below 4
chars, so a short name never sheds its ending. Consonant-final ones are fine —
the free case tail `[а-яіїєґ]*` covers everything. Vowel-final ones are not:
«Мена» never reaches «мену»/«мени», «Ічня» never reaches «Ічню»/«Ічні». Both
carry explicit aliases. The remaining vowel-final short entries (Ушня, Тур'я,
Буда) have no inflected form in the corpus yet — and Буда must stay that way,
because «буду» is a verb (53 hits) and «буди» sits inside «будинок» (27).

**Multi-word names cannot match as one stem** — `_stem()` strips spaces, so
"великадимерк" never appears in text. Such an entry matches only through a
single distinctive one-word alias: «димерка», «щимель», «устя», «млини»,
«липів», «бакланов», «маличина», «хатилова», «селянська», «трисвятська». If no
single word is both distinctive and safe, the entry cannot be added at all (see
Красна Гірка below).

The same is true of a multi-word **alias**, which is the trap: it looks like it
works and silently never fires. Лівобережний carried «лівий берег» for the life
of the project and matched not one of the 102 bank callouts; «Русанівські сади»
and «Нижні Сади» were in the list with no alias at all, i.e. unmatchable by
construction. `test_toponyms.py::test_every_entry_is_reachable_by_its_own_name_or_an_alias`
now fails on any entry no text can reach. When the distinctive half is an
ordinary adjective, the way in is a whole-word alias per case form, pinned to
the following noun if it needs one — see «лівий/правий» and `_ALIAS_NEXT_WORD_REQUIRED`.

**Longest matched stem wins an overlap.** Two entries matching at the same
offset are ranked by how much of the word each explains, `prefer_region` only as
the tie-break. This is what keeps «Пирогівці» off «Пирогів», «Понорниця» off
«Понори», «Коропʼє» off «Короп», «Березанка» off «Березань». It also works
*against* you: «Оболоння» (a northern village) explains more of «над Оболонню»
than Kyiv's «Оболонь» does, which is why that one needs `region_only`.

Ranking uses the stem that actually fired, not the entry's longest stem —
otherwise an entry with one short alias claims specificity it has not earned.
Live example: «Морівськ» lost to «Район моря», whose 4-letter alias «морі» is a
prefix of it but which advertised the 8 chars of «районмор».

**Sub-4-character names need `vocab._WHOLE_WORD_ALIASES`** to match at all
(«ЧЗВ»). Whole-word matching is also the fix when a valid stem is a prefix of an
ordinary word: «центр» (⊂ центральний, укргідрометцентр), «пох» (⊂ похолодання),
«голос» (⊂ голосно), «бц», «прогрес» (⊂ прогресу), «замістя» (⊂ замість),
«розсудів» (⊂ розсуд), «антонов» (⊂ Антоновичі).

**Guards in the matcher, not in the data.** Some collisions are resolved by
`matcher.py` rather than by dropping an alias:

- `_is_street_reference` — «вул. Антоновича» must not match Нивки's «антонов».
- `_is_foreign_sea` — «Чорного моря» in a strategic report must not match «Район моря».
- `_is_airbase_reference` — «аеродром «Українка»» is a Russian bomber base in
  Amur Oblast, named in 20+ stored reports. **Українка's entry ships only
  because this veto exists; do not remove one without the other.**
- `_is_oblast_form` — «Чернігівщина» must not match the city «Чернігів».
- `vocab._ALIAS_PREV_WORD_REQUIRED` — «церкв» matches Біла Церква only after a
  «Біл…» word, or «приліт у церкву» would pin a strike 80 km out of town.
  «перемоги» matches Суми's Проспект Перемоги only after «просп…».
- `vocab._ALIAS_NEXT_WORD_REQUIRED` — the third of the set: «зелений»,
  «блакитні» and «старе» count only before «гай», «озер…» and «сел…». This is
  what makes a spaced name shippable when the DISTINCTIVE half is the first word
  and the second is generic — the case that would otherwise be the Красна Гірка
  rejection below.

The three are keyed by the MATCHED TEXT and so apply to every entry that matched
it, not to one entry. That is enough while one entry owns the word.

### Two entries, one word — `match_context`

When TWO entries share their only matchable word, a rule keyed by the word
cannot help: the rule that saves one is exactly the rule that must not apply to
the other. `match_context` puts the rule on the ENTRY instead, keyed by the alias
it governs, so each side states its own half:

```python
{"name_uk": "Велика Писарівка", …, "aliases": ["великописарівськ", "писарівк"],
 "match_context": {"prev_required": {"писарівк": ["велик"]}}},
{"name_uk": "Писарівка", …, "aliases": [],
 "match_context": {"prev_veto": {"писарівк": ["велик"]}}},
```

Four keys, mirroring the global set: `prev_required`, `prev_veto`,
`next_required`, `next_veto`. `*_required` drops the match when the neighbouring
word is absent, `*_veto` when it is present. An alias key governs itself plus a
**case tail** and nothing else (`matcher._governs`), so a rule written for an
entry's ambiguous alias leaves its unambiguous ones alone («великописарівськ»
above needs no qualifier). Plain `startswith` was enough while every rule keyed a
stem, and stopped being when ТЕЦ-5 took a bare «тец» rule: the name's own
«тец-5» starts with it too, so the plant disqualified itself for lacking the
digit it already carried.

The three cases in the list, all measured on the stored corpus:

| Pair | Apart | Was |
|---|---|---|
| Писарівка / Велика Писарівка | 80 km | a global veto kept the bare village's 41 callouts and silenced the other's 24 |
| Верхня / Нижня Сироватка | 9 km | only Верхня had «сироватк», so every Нижня callout landed on Верхня — a wrong pin, not a gap |
| Деснянське / Деснянський район (Чернігів) | 126 km | the village had «деснянськ» to itself, so «На Деснянський р-н» pinned the raion onto it |
| Нові / Старі Боровичі (2026-08-30) | 6.5 km | neither existed; all 9 corpus callouts carry the qualifier, so both sides `prev_required` it and a bare «Боровичі» stays a candidate |

An unqualified form now matches **neither** side and reaches the coverage queue —
«Сироватка» alone is the live example, and the corpus has never produced one.
This is the usual trade: unmatched is where it already was, a wrong pin is a new
lie. `districts.match_context` is a JSON column (migration 0035) and is re-synced
from the gazetteer on every boot, like `aliases` and `region`.

There is deliberately no global `PREV_WORD_VETO` any more: its only case was
«писарівк», and that case is precisely the shape a global dict states wrongly.

---

## Adding an entry: the procedure

Four steps, none optional. Two of the four exist because skipping them has
already shipped a bug.

1. **Geocode** via `scripts/geocode_localities.py` (Nominatim, ≤1 req/s, real
   User-Agent). Confirm the point is in the oblast you expect. If Nominatim
   returns several candidates, **let the neighbouring callouts decide** — the
   places named in the same minutes localize the corridor. That is how Блистова
   resolved to the Novhorod-Siverskyi one (its neighbours cluster at 51.88–52.00)
   and how Курилівка resolved to the **Nizhyn** one, overturning what the name
   alone suggested.

2. **Sweep the stem over the whole stored corpus** before committing. This is
   the mandatory step. It is how «Понорниця» was found (its stem is a prefix of
   «Понори»), how «Високе» was rejected, and how «Рембаза» was caught being on
   the wrong region's candidate list.

3. **Check the name is not already in the list.** Trivial, and skipped once:
   the 2026-08-24 batch re-added Блистова, Дуболугівка and Омбиш, which already
   existed. `tests/test_toponyms.py` now guards this.

4. **Run the before/after resolution diff** over the corpus and read it. The
   expected shape is *every changed message gains a district that resolved to
   nothing, and no existing match moves*. A candidate that changes **nothing**
   is not a no-op — it means the name already resolves, i.e. you are about to
   add a duplicate.

Also check the coverage-gap queue would still propose the name if it were
absent (`tests/test_toponyms.py::test_stoplist_would_still_propose_every_known_place`).
A stop word that is a prefix of a real name silently costs the next such
village: the numerals alone cover Трипілля («три»), Семиполки («семи») and
Троєщина («троє»); «борщ» was rejected from the chatter list for eating
Борщагівка; «пара» was moved to whole-word matching for eating Парафіївка.

---

## The failure classes

**A missing chain root is the most expensive gap there is.** `_dispatch` drops
an unlocalized message at step 2b, *before* `find_track_by_reply` runs. So a
reply naming a village we do not have never reaches the tracking layer: the
parent track never learns the target moved, and every further reply down that
chain is orphaned too. «Деміївка 🔴» → «Совки/Солома/Жуляни 🔴» → «Чабани/Боярка
🔴» was one drone crossing the city as three unrelated tracks. Same shape:
«Рогівка зайшов» → «На Смяч», «Бобрик» → «На Держанівку», «На Терехівку» (raw
8941).

**A short stem eats an ordinary word.** The canonical case is «Остер» ⊂
«остерігайтеся». Four-letter stems are where this bites.

**A Kyiv stem swallows a northern toponym.** The spoken word is *longer* than
the Kyiv entry's stem and denotes a different place 150 km away: «Мезин,
деснянське» became the Деснянський **raion** of Kyiv and opened a Kyiv attack
banner; «На Оболоння на короп» became Оболонь; «Чайкине на жадове» became Чайки;
«Пирогівці» became the Kyiv museum Пирогів; «Понори на Обухове» became Обухів;
«Березанка» became Березань; «Деснянка» became смт Десна. The fix is always an
entry of its own, sometimes plus `region_only`.

**A homonym across the oblast border.** Same name, both oblasts, and the text
never says which — the reporting channel's region does. Лебедівка, Рокитне,
Дніпровське, Вишневе, Димерка. Adding only one side hijacks the other: 20 corpus
messages say «Димерка», all of them Kyiv channels pairing it with Бровари, and
every one was resolving to Димер 47 km away on the wrong side of the city.

**A name that is also a common word.** See the two tables below.

---

## Names deliberately NOT added

Re-adding one of these is a regression. If new evidence justifies a reversal,
say so explicitly and record the new sweep.

| Name | Why not |
|---|---|
| **Остер** | Stem `остер` ⊂ «остерігайтеся». Козелець on the same M-01 axis covers the corridor. *(The village was later added as a `chernihiv` entry — the rejection stands for any Kyiv-side use.)* |
| **Високе** | 24 corpus hits, ~2 the village: `висок` eats «висока загроза», «на висоті», «летить не високо», «високопосадовці». The Остер failure exactly. |
| **Світанок** | A real village, but «на світанок» / «до світанку» is what this genre says about the end of an alert. Whole-word matching cannot help — the phrase uses the same word form. *(Added 2026-08-24 on a clean sweep, then reverted: the rejection predates it and the failure mode is realistic.)* |
| **Заспа** (bare, as a STEM or as its own entry) | Stem `засп` fires inside «заспокоїтись», and a different village Заспа ~45 km away means a standalone entry has to put a point on one of the two. *(Reversed in the only form that dodges both, 2026-08-27 — see the row in "kept under watch". The rejection stands for a stem and for a separate record.)* |
| **Віта** (bare) | `віта` ⊂ вітаю / вітання. Віта-Поштова matches on its hyphenated compound only. |
| **ТЕС** (bare) | ⊂ тест / тесля. Трипільська ТЕС rides on «трипіл». |
| **ТЕЦ** (bare, Kyiv) *(reversed 2026-08-30 — see below)* | Tried 2026-08-21 and reverted. As a whole-word alias it survives «тец-6», but the corpus also spells it «ТЕЦ - 6» spaced, where the bare alias matched and ТЕЦ-6's hyphenated stem did not — a message went from matching nothing to matching the wrong plant 12 km away. The Chernihiv «ТЕЦ» is unaffected: it is `region_only`, so it never meets a numbered form. **The reversal:** each Kyiv plant now takes the bare alias *and* `match_context.next_required` on its own digit, so «ТЕЦ 5» → ТЕЦ-5, «ТЕЦ - 6» → ТЕЦ-6, and an unnumbered «ТЕЦ 🔴» still matches neither. 8 dead messages recovered; the wrong-plant failure is unreachable by construction rather than by luck. |
| **Південні** (Kyiv) | 8 bare «Південні 🔴» callouts, always beside a southern place (Козин, Іподром, Васильків) — but it is the channel's *direction*, not a settlement, and the message «Південні регіони — був пуск» uses the same word for half the country. Directional callouts are `domain/origins.py`'s business, not a pin. |
| **Борщ ага** (Kyiv) | Three messages where the channel's own «Борщага» came out split by an autocorrect. Unfixable in this layer: any rule keyed «борщ» governs Борщагівка's real 98 callouts too (`_governs` matches an alias plus its case tail), so the fix would silence the name it is trying to reach. |
| **Сніжки** (Сумщина, 2026-08-30) | A real village with 2 clean callouts, and the sweep is clean — but the corpus only covers July–August, and «сніжки» is a winter noun the sweep structurally cannot have seen. Whole-word matching cannot help: the noun IS the same word. The Веселе rejection, one season away. |
| **Морів** (Чернігівщина) | The channel's truncation of Морівськ, which is already an entry and matches its full form 3 times. As an alias «морів» is also the genitive plural of «море», which the «Район моря» entry already fights over. One truncated callout is not worth re-opening that. |
| **Харитонівка, Панфіль, Соснова, Мала Загорівка** (Чернігівщина, 2026-08-30) | One callout each, no neighbour in the same minutes to place them, and several of the names exist more than once in the oblast. The bar is the same one Тростянка/Дмитрівка were held to and later cleared. |
| **Медвин** (Kyiv) | One corpus mention, and it contradicts itself — «Йде наразі на самий північ в район Медвин», while the only Медвин in the oblast is 120 km SOUTH. One hit that points the wrong way is an anecdote. |
| **зона** (bare) | Common noun. Чорнобильська зона uses «чзв» + «чорнобиль». |
| **Красна Гірка** | Two-word, and neither word is safe: «гірк» is how this channel names a *different* settlement (Гірки), and «красн» swallows «Краснодарського», an ORIGIN mention `domain/origins.py` owns. |
| **Хороше Озеро, Червоне Озеро, Велика Доч, Мала Дівиця, Зелений Гай, Великий Щимель** (as spaced names) | No distinctive single word; the shared «озеро» is generic (5 unrelated corpus hits). Великий Щимель ships only because «щимель» itself is distinctive. |
| **Гути** *(decoded 2026-08-27 — now an alias on Василева Гута)* | It is the channel's plural for the Василева/Хатилова pair, and the channel decoded it itself: the corridor bulletin (raw 6589) reads «…Славутич/Неданчичі ➡️ **Боровики/Гути** ➡️ Десна/Остер», and Боровики is 2.1 km from Василева Гута, while Лошакова Гута sits 30 km on — 14 km from Десна, i.e. in the *next* stage. Worst case the pin lands 2.3 km off, on the pair's other half. Whole-word alias; the three `-Гута` entries keep their own full-name callouts. |
| **Наливайківка** (in-city Sviatoshynskyi) | Not resolvable: every query variant matches the same-named village in Bucha raion ~45 km away. The oblast village *is* in the list. |
| **Романівка** (2026-08-27, with Стоянка) | One corpus mention, and it is a *district of Ірпінь* — the Ірпінь entry already sits 3.8 km away, so the gap it would close is smaller than this map's own precision. The name is also among the most common in the country, which makes a future homonym likelier than a future callout. |
| **Замістя / Розсудів** | Stems eat «замість» and «на власний розсуд» — kept, but as whole-word entries. |
| **Печі** | The only Печі in the oblast is 100 km from the Остер it was called out with; the word is also the plural of «піч». |
| **Селище** | Six in the oblast, none on a corridor, and the channel uses the generic noun too. |
| **Тростянка, Дмитрівка** (2026-08-20 pass) | Several in the oblast, none clearly the one meant. *(Both later resolved and added once more callouts settled it.)* |
| **Берелівка, Городище, Полісся** (2026-08-20 pass) | No point / ambiguous / also a region-wide noun. *(Берилівка — the spelling Nominatim does have — and Городище were added on 08-22.)* |
| **летовище** (Nizhyn airfield) | A common noun, and local airfield defence is not this map's business. *(The Chernihiv «Летовище» later shipped as `region_only`.)* |
| **Хорівля, Красяни, Івнівка, Поусівка, Круги, Тальне, Шишки** | Nominatim has no point in Чернігівська область. |
| **Жужики** (Сумщина, 2026-08-28) | Not a place. All 8 corpus hits are the channel's slang for OUR OWN drones — «це жужики наші в Сумах, спокійно», «звуки які ви чуєте це наші жужики». Ranked 40th on the mining list and would have shipped without the sweep. |
| **Лука / Велика Лука** (Сумщина) | Two different places 60 km apart in the same corpus, and 1 of the 6 hits of the bare word is «стріляє із лука» (a bow). Nothing distinguishes them, so one of the two would always be wrong. |
| **Береза** (Глухівська громада) | Stem `берез` swallows «березня» — the month, which every dated report carries. Exactly the Остер failure, and the village has 2 corpus hits against it. |
| **Веселе** (Сумщина) | `весел` eats «веселка»/«веселий»; 3 hits, and Веселе is among the commonest names in the country. |
| **Епіцентр** (Суми) | The store IS a landmark the spotters use, but only 1 of its 2 corpus hits is the Sumy one — the other is the Melitopol store being burned in a news post. Чернігів's Епіцентр ships because its feed names it 6 times. One usable hit is an anecdote. |
| **Еспланадна** (Суми) | 3 callouts, and Nominatim has no point for the street under any spelling tried. |
| **Герасима Кондратьєва** (Суми) | 3 hits, but 2 are postal addresses in a fundraising post and a road-closure notice. One real callout. |
| **Люлецька, Чорновола, Мазепи…** (streets, as a class) | A street is a line across a whole city, not a point, and every one of those names exists in Kyiv too. Some later shipped as `region_only` city landmarks where the spotters really do narrate at that granularity. |
| **Нафтобаза, Земснаряд, Тероборони** | Bare city objects, same problem as streets. |

## Entries kept under watch

Each of these collides with an ordinary word and survives **only** because a
corpus sweep found zero bad matches. Re-sweep if the feed changes.

| Entry | Collides with | Sweep result |
|---|---|---|
| **Щасливе** | щасливий / «будьте щасливі» | zero bad matches |
| **Рогозів** | рогоза (cattail) | zero |
| **Пирогів** | пироги / пиріг | only the museum |
| **Совки** | «совковий» | 1 hit, the callout itself; the collider appears zero times |
| **Солома** (Солом'янський alias) | солома (straw) | all 11 forms are the raion |
| **Вишня** (Вишневе alias) | cherry | all forms are the town |
| **Море / моря / морі** | морально, мороз | 8 genuine calls; the only false hit is a foreign sea, vetoed in the matcher |
| **Водосховище** | other Dnipro reservoirs | 2 occurrences, both this one |
| **Стоянка** (2026-08-27) | «стоянка» = a parking lot | 6/6 corpus hits are the village, named by four different channels. «автостоянка» is structurally safe — the matcher anchors on a word start — so only the bare noun could ever collide, and it never has. Pinned by a test either way. |
| **Заспа / Заспу / Заспи** (Конча-Заспа aliases, 2026-08-27) | «заспокоїтись» as a stem; a second Заспа 45 km south | 15/15 corpus hits are Конча-Заспа. Whole-word only, so the verb is unreachable; aliases rather than an entry, so no second point exists to be wrong. «Конча-Заспа» still resolves to ONE hit — both branches are the same id. Two tests pin the verb (`test_parser.py`), three pin the callouts. |
| **Пуща** | «запущено», «пуски» | blocked by the word-start boundary |
| **Глухів** (2026-08-28) | «глухий»/«глухо» — «глухий вибух» is a phrase this genre plausibly types | zero hits in 13.6k messages; all 20 are the town. `region_only`, so only a Сумщина channel can reach it |
| **Терни / Річки / Садки / Низи / Вири** | `терн` ⊂ Тернопільщина + Тернівка; `річк` ⊂ «річка»; `садк` ⊂ «садків»; `низи` ⊂ «низина»; `вири` ⊂ «вирив» | Терни, Річки and the poplar/«сад» family are whole-word (see the vocab notes); Низи 21/21 and Вири 16/16 are clean as stems |
| **Земляне, Мозкове, Синяк, Спаське** | ordinary-looking adjectives/nouns | 3–7 hits each, every one the settlement |
| **Верхня Сироватка** (one entry for a pair) | Нижня Сироватка 9 km away shares the only alias «сироватк» | 36 hits, 27 of them the upper village; the 4 lower ones land 9 km off, the Гути trade one raion wide |
| **Лівий / Правий берег** (2026-08-30) | «прав» and «лів» sit inside «правил», «правоохоронних», «правильно», «ліворуч» | Whole-word, and only the four case forms the feed types. «Праві»/«правій» are deliberately absent — their only hits are «праві смуги»/«правій смузі», a road-closure notice. 102 callouts recovered; six news items that name a bank in the city-news register are dropped by new `_AFTERMATH`/`_CIVIC_NOTICE` words added in the same pass |
| **Хотів** (2026-08-30) | the past tense of «хотіти» | 6 callouts against 3 verbs, and no property of the word separates them — the entry vetoes the function words only the verb takes («хотів у вас…», «хотів би…», «хотів її…»). Pinned by a test on all three verb sentences |
| **Лавина** (2026-08-30) | «лавина» = an avalanche | 3/3 corpus hits are the mall on Берковецька, used as a landmark exactly like Sky Mall |
| **Золоті** (Золоті ворота, 2026-08-30) | the plural adjective «золоті» | Whole-word, so the stem «золот» cannot reach Чернігівщина's «Золотий берег» beach; 7/7 hits are the callout, and the full name never appears |
| **Березна / Березну** (2026-09-02) | «березня» — the MONTH — sits under the stem «березн» | Whole-word, both case forms the feed types; 11/11 corpus callouts survive and the month is unreachable. Safe as a stem only while Чернігівщина's own channel was the only reader: it does not repost policy news, and raw 1255 («до березня 2028 року») is a Kyiv channel doing exactly that. Found by sweeping the `extra_regions` binding BEFORE turning it on |
| **Славутич** (2026-09-02) | «ЖК "Славутич"», a housing estate on Позняки 150 km from the town | `prev_veto` on «жк», the narrowest guard that works — every other form («зі Славутича», «повз Славутич», «на Славутич») keeps matching. 1 corpus hit, an aftermath recap listing where drones landed. Same sweep as Березна above |
| **Охоче** (Харківщина, 2026-08-30) | «охоче» = willingly | 8/8 corpus hits are the village, named inside the Таранівка→Красноград corridor bulletin by both Kharkiv channels. The adverb has never appeared; re-sweep if the feed changes |

---

## How the list grew

Reactively, from real feed gaps. Each pass is recorded in git; the short version:

| Pass | What it added |
|---|---|
| Initial | 10 Kyiv raions + microdistricts spotters name directly. |
| 07-09 | In-city micro-neighbourhoods + approach villages, mined from `eval/ground_truth_sessions.json`. |
| 07-18 | Mass-attack gaps — real callouts with no entry. |
| 07-31 | Southern / SW approach villages from a reactive-Shahed incursion. |
| 08-17 | Far-northern corridor (Chornobyl zone, Страхолісся) — drones entering from Belarus. |
| 08-18 | Southern staging ring (Біла Церква, Рокитне, Тараща, Богуслав, Миронівка) and spotter shorthand («ПОХ», «Торгмаш»). |
| 08-19 | **G** — Чернігівщина corridor, mined from 300 messages of the northern channel. Took that feed's rule coverage from 20% to 72% and two-place (vector) messages from 2 to 58. |
| 08-20 | Second Chernihiv sweep — the eastern half of the oblast (Прилуки / Бахмач / Борзна), plus the chain-root fixes (Рогівка, Леньків). |
| 08-21 | **J** — a Chernihiv **city** layer, which did not exist: the spotters narrate a drone across Чернігів exactly as the Kyiv channels narrate one across Київ. ~100 entries recovered 121 of 200 dead messages. **J3** added the `region_only` landmarks (ТЕЦ, вокзал, летовище). |
| 08-22 | **K** — the ring and corridors *around* Чернігів, at village granularity. **K2** — the morning Бахмач→Борзна→Ніжин→Носівка run. |
| 08-23 | **L** — cross-region audit: the names that made the northern channel produce a *Kyiv* target. **M** — whole-corpus gap pass (Мамекине, Лісконоги, Kyiv's Вокзал, Українка). **N** — the Новгород-Сіверський loitering session, all reply-chain gaps. |
| 08-24 | Mined against the stated-path flag (`rules._movement_path`): each entry was the unresolved end of an «A на B» callout, so the gap cost a whole vector rather than a pin. Plus Яцево / Терехівка from the raid over Чернігів itself. |
| 08-28 | **S** — Сумщина's first layer, and the region's activation. 137 entries mined from 3760 messages of its two spotter channels, which localized **0%** before (the region shipped declared-and-empty in 0.38.0) and **64%** after. Three groups, the same shape the north took over three passes: raion/hromada centres, the Сумський-район border belt where the КАБ and FPV traffic is, and a Суми CITY layer. It also needed two new context hooks (`_ALIAS_PREV_WORD_VETO`, `_ALIAS_NEXT_WORD_REQUIRED`) and unmuted eight names the coverage-gap stoplist had been hiding. |
| 08-30 | **T** — the first pass mined over the WHOLE stored corpus rather than a recent window: every unlocalized spotter message re-parsed with the current gazetteer, unknown words ranked by frequency. 21 Чернігівщина entries, all from one channel and all still dead after eight previous passes — Виблі, Халявин, Солонівка, Черниш, Кошівка, Підгірне, Лукашівка, Пакуль, Ковчин, Єньків, Жовідь, Товстоліс, Салтикова Дівиця, Нові/Старі Боровичі, Корчев'я, Загороднє, Петрики, Скитьки, Кузничі, Минаївщина, plus the «сновсок» alias. 93 messages change, 82 gain a first match, nothing moves. Six of them are the far end of an «A на B» vector, so the gap was costing a route. Triggered by raw 13578 «Петрики , Скитьки 3», which produced nothing while the same channel's next three callouts became tracks. |
| 08-30 | **U** — second Харківщина pass off the same whole-corpus mining. Nine settlements + the Шевченківський/Холодногірський city raions (`region_only`, since Kyiv owns a Шевченківський). 13 messages change, 12 gain a first match, nothing moves. The east-of-the-city corridor «Верхня Роганка → Елітне/Зернове → Кулиничі → ХТЗ» was one target with three dead callouts in the middle. Four rejections came out of the same list and are half the value: Довжик (three in the oblast, its two callouts point opposite ways), Проходи (`проход` ⊂ «проходить», 17 of 19 hits the verb), Варварівка and Петрівка (several each, one callout, no neighbour). Also the first *documented reversal by re-geocoding*: «Елітне» had been rejected because Nominatim answered Зернове — queried with its raion it answers Елітне, 1 km from Зернове, and the corridor confirms both. |
| 08-30 | **V** — the first whole-corpus pass over **Київщина** itself, the region every earlier pass had assumed was done. 9 entries + 4 aliases, and most of the value was not new villages but names the list already had and could not reach: «Лівий/Правий берег» (102 callouts, the old alias was a spaced form that can never stem), «Русанівські сади» (in the list since July with no alias, unmatchable), and both ТЕЦ in their spaced spelling. New: Коцюбинське — which Чернігівщина's Михайло-Коцюбинське had been claiming from 12 Kyiv callouts, a wrong pin 130 km out — plus Хотів, Лісники, Київська ГЕС, Золоті ворота, ВДНГ, Лавина, and «хрещатик»/«голосіів» aliases. 171 messages gain a first match, 40 gain a second place, **nothing moves**, and two long-standing false positives (a «сильний дим після удару» advisory over Борщагівка/Троєщина, a «звуки які може чути Оболонь та Вишгород» explainer) stop raising tracks. |
| 08-30 | **W** — the first batch mined by the **coverage queue itself** rather than by a script, the same day that queue stopped ranking channel signatures above villages (`api/coverage.py`). 8 entries + the «лозівськ» raion alias, from three regions at once: Охоче (Харківщина, 8 callouts in the Таранівка→Красноград corridor), the Ріпки–Любеч strip Паперня/Строївка/Ільмівка/Гучин/Листвен (Чернігівщина, one corridor whose every stage was dead), and Авраменкове (Сумщина). Володимирівка came last and separately — 9 callouts, the most-named unlocalized place in the whole corpus, and it was missed on the first pass through this very list; the operator caught it live the same afternoon. 38 messages change, 21 gain a first match, 17 gain a second place, nothing moves. Four rejections came off the same list and are recorded above — Сніжки is the interesting one: a clean sweep over a July–August corpus says nothing about a winter noun. |
| 08-27 | Глузди + Горбове — a Куликівка pair 4.5 km and 9 s apart, one target that produced nothing at either end. Plus the Заспа aliases: the first *reversal* of a documented rejection, allowed only because the whole-word/alias form dodges both of its reasons. Then «Гути», decoded off the channel's own corridor bulletin — three of its five callouts are «A на Гути», so the gap was costing a whole route, not a pin. And Стоянка on the Zhytomyr highway, where the nearest entry was 7.8 km off. |
| 08-31 | **X** — two names off one live callout, «На Книжичі/Проліски 🔴» (raw 15104), which localized to nothing. Only one of them was a new place. **Проліски** is real (Бориспільський р-н, 50.3921/30.7796) and needed the Ріпки-class alias «пролісок» — the genitive plural drops the и and grows an о inside the root, which is the form the channel used in its other callout, «У район Бортничів/Пролісок». **Книжичі** is not a village at all: OSM has no `Книжич*` node anywhere in the oblast, while «Княжичі» — already an entry, 7.6 km from Проліски — has 19 correct corpus callouts on exactly that Бровари/Бориспіль corridor. One letter, and «книж» occurs in the whole 13k-message corpus only inside that typo, so it ships as an alias rather than as a phantom pin. 2 messages change, both gain, nothing moves. |

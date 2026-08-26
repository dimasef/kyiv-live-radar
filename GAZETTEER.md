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
| **Заспа** (bare) | Stem `засп` is 14/15 clean, but the 15th is «заспокоїтись», and a different village Заспа ~45 km away breaks geocoding. Конча-Заспа rides on the «конча» alias instead. |
| **Віта** (bare) | `віта` ⊂ вітаю / вітання. Віта-Поштова matches on its hyphenated compound only. |
| **ТЕС** (bare) | ⊂ тест / тесля. Трипільська ТЕС rides on «трипіл». |
| **ТЕЦ** (bare, Kyiv) | Tried 2026-08-21 and reverted. As a whole-word alias it survives «тец-6», but the corpus also spells it «ТЕЦ - 6» spaced, where the bare alias matched and ТЕЦ-6's hyphenated stem did not — a message went from matching nothing to matching the wrong plant 12 km away. The Chernihiv «ТЕЦ» is unaffected: it is `region_only`, so it never meets a numbered form. |
| **зона** (bare) | Common noun. Чорнобильська зона uses «чзв» + «чорнобиль». |
| **Красна Гірка** | Two-word, and neither word is safe: «гірк» is how this channel names a *different* settlement (Гірки), and «красн» swallows «Краснодарського», an ORIGIN mention `domain/origins.py` owns. |
| **Хороше Озеро, Червоне Озеро, Велика Доч, Мала Дівиця, Зелений Гай, Великий Щимель** (as spaced names) | No distinctive single word; the shared «озеро» is generic (5 unrelated corpus hits). Великий Щимель ships only because «щимель» itself is distinctive. |
| **Гути** | No Nominatim point, and it collides with the three `-Гута` entries. Almost certainly the channel's shorthand for one of them — a decoding question for the maintainer, not a guess. |
| **Наливайківка** (in-city Sviatoshynskyi) | Not resolvable: every query variant matches the same-named village in Bucha raion ~45 km away. The oblast village *is* in the list. |
| **Замістя / Розсудів** | Stems eat «замість» and «на власний розсуд» — kept, but as whole-word entries. |
| **Печі** | The only Печі in the oblast is 100 km from the Остер it was called out with; the word is also the plural of «піч». |
| **Селище** | Six in the oblast, none on a corridor, and the channel uses the generic noun too. |
| **Тростянка, Дмитрівка** (2026-08-20 pass) | Several in the oblast, none clearly the one meant. *(Both later resolved and added once more callouts settled it.)* |
| **Берелівка, Городище, Полісся** (2026-08-20 pass) | No point / ambiguous / also a region-wide noun. *(Берилівка — the spelling Nominatim does have — and Городище were added on 08-22.)* |
| **летовище** (Nizhyn airfield) | A common noun, and local airfield defence is not this map's business. *(The Chernihiv «Летовище» later shipped as `region_only`.)* |
| **Хорівля, Красяни, Івнівка, Поусівка, Круги, Тальне, Шишки** | Nominatim has no point in Чернігівська область. |
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
| **Пуща** | «запущено», «пуски» | blocked by the word-start boundary |

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

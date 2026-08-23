# Known failure classes and where each one lives

Read this when a finding needs a home in the code. It is a map, not a rulebook —
a new failure that fits none of these is the interesting kind.

`WORKFLOW.md` (repo root, Ukrainian) is the full pipeline walkthrough with the
maintained weak-point list. Read it before touching `app/parsing/rules.py` or
`app/domain/tracking.py`.

## Table of contents

- [False positives — something surfaced that shouldn't have](#false-positives)
- [False negatives — something real was dropped](#false-negatives)
- [Tracking — right sightings, wrong grouping](#tracking)
- [Ingestion order — the message arrived late](#ingestion-order)
- [LLM spend](#llm-spend)
- [Things that look like bugs but are decisions](#things-that-look-like-bugs-but-are-decisions)

---

## False positives

The parser is a curated word-list machine, not NLP. Nearly every FP is a missing
entry in one of the message-level suppression filters in `app/parsing/rules.py`,
and the fix is usually one phrase plus one test.

| Shape | Where | Real example |
|---|---|---|
| Aftermath/casualty news read as a live target | `_aftermath` | "У Шевченківському районі часткове руйнування" |
| Donation/ad post | `_promo`, `_ad_action` | "Банка на дрони-перехоплювачі" |
| Civic/transport news naming a place | `_civic_notice` | "змінять маршрути тролейбусів" |
| Negation | `_negated` | "це не БПЛА", "більше не фіксується" |
| Day recap / attack tally read as live | `_day_recap`, `_summary` | "загалом було до 35 ракет" |
| Terse pulse attaching to the wrong thing | `_target_pulse` | "Ціль на Сумщині" joined a KYIV track (fixed: it now checks `target_elsewhere`) |
| Other oblast as the TARGET | `domain/origins.py::target_elsewhere` | "Ціль на Дніпро" — note "з Курщини" is an ORIGIN and must still pass |
| News on the alert channel read as a siren | `parsing/alert_parser.py::_START_RE` | a metro news post quoting "оголошення повітряної тривоги" opened a real alert |
| Gazetteer stem collision | `app/gazetteer.py` | "Остер" matched "остерігайтеся" |

Adding a gazetteer entry is the one change that always needs a corpus sweep
first — a short stem can match an unrelated common word. `app/gazetteer.py`
documents the ones already rejected for this reason.

## False negatives

Harder to see, because nothing appears anywhere. Find them by reading the
`## Silent messages` section of the report (`--texts`) rather than by counting.

- **Type stated without a place.** "Циркон", "обидва реактивні" — carries type
  information for tracks already open, currently dropped unless a citywide
  track exists to corroborate (`handlers.py::_handle_target_pulse`).
- **Missing gazetteer coverage.** The single biggest lever on accuracy, far
  ahead of the LLM. `eval/mine_toponyms.py` finds candidates; the admin console
  has a «Прогалини» tab fed by the same gate.
- **Impact/explosion cues.** "Гучно", "Падають" — deliberately unmapped, see the
  decisions section below.

## Tracking

`app/domain/tracking.py` is the most failure-prone layer. Priority order:
reply-threading, then same-district corroboration inside
`corroboration_window_minutes`, then a new track. Both the window and the
match-latest-only behaviour were tuned empirically against
`eval/track_eval.py` — treat them as measurements, not guesses.

- **Split**: one real target became several tracks. Usually a broken reply chain
  (see below) or a channel that never uses replies. The commonest way a chain
  breaks is a GAZETTEER gap, not a tracking bug: `_dispatch` drops an
  unlocalized message at step 2b, *before* `find_track_by_reply` runs, so a
  reply naming a village we don't have never reaches the tracking layer at all
  — the parent track never learns the target moved, and every further reply
  down that chain is orphaned too. Confirm with `parse_message` on the reply's
  text before proposing anything in `tracking.py` (2026-08-23: «Рогівка
  зайшов» → «На Смяч», and 08-20 «БпЛА біля Рогівки» before it).
- **Merge**: several targets in one track. The failure mode the current design
  exists to prevent; regressions show up as `TRACK PURITY` falling.
- **Type churn** inside one track (the report lists these) comes from
  `context.py::_note_and_inherit_type` (per-channel, 5 min) and
  `core.py::_infer_incident_type` (incident-level). Fusion surfaces genuine
  disagreement as a conflict rather than silently overwriting.

Never change grouping without running `eval/track_eval.py` before and after and
quoting both numbers.

## Ingestion order

Telegram replays history on every reconnect, so a message can be stored long
after it was posted. Two live incidents came from acting on those as fresh:

- a 00:14 sighting stored at ~00:28 opened a third track and a **new incident
  ten seconds after the all-clear**;
- a відбій ingested before the alert start it belonged to left a phantom alert
  hanging for two hours.

The guard is `IngestContext.arrived_late()` plus `_only_closes()` in
`handlers.py::_dispatch`, and the `start`-only veto in `ingest/alert.py`. It is
opt-in (`enforce_age`) because reprocess and the replay feed legitimately re-run
whole old corpora. A late message may still CLOSE things — recovering a missed
відбій is why backfill exists at all.

## LLM spend

Two independent paths, and a fix aimed at the wrong one changes nothing:

- **inline fallback** — `ingest/resolve.py::should_fallback`, runs during
  ingest, only for a threat-flavoured message with no district;
- **async triage** — `pipeline/triage.py::should_triage`, picks up the
  *suppressed* classes (negated, aftermath, day_recap…) for a second look.

**A `triage_state` does NOT mean the call came through triage** — that was wrong
and cost one analysis a completely inverted split (reported 0 inline / 23 triage
where the truth was ~15 / 8). `should_triage` deliberately returns True when an
inline verdict already exists ("inline call ran, didn't localize — reuse it"),
and `_process_job` then stamps `triage_state`/`triage_action` on that row while
leaving the cost fields the inline call wrote. Both paths end up stamped.

What the export actually supports: `suppressed_by` is decisive at both ends — a
triage-only suppressor flag (negated/aftermath/civic_notice/eppo_marks/
siren_only/political_quote/day_recap) means triage paid, and `no_district`/
`not_threat` means the inline fallback did, since those are the no-flag
fall-through labels that `should_triage` won't enqueue on its own. The gap is
rows that produced an event or a notice: `raw_query.py` blanks their
`suppressed_by`, and nothing else records the path, so the report calls those
**undetermined** rather than guessing. Settle one by re-running
`should_fallback` on its text.

There is a THIRD consumer and it is now the highest-volume one: the target-type
classifier, `core.py::_maybe_llm_type` (~1.7k tokens, ~$0.0018 a call). Its
answer is written back into the per-channel type context
(`context.py::note_inferred_type`), so a run of bare toponyms pays once per
inheritance window, not once per message. If an export shows the same channel
buying the same verdict every few minutes, that feedback is what broke — check
it before blaming the window length.

`llm_attempted=True` with NULL tokens/cost means the call was made and never
returned (timeout, network, API error). It is NOT "no call": before 2026-08-23
the flag was only set on a completed response, so a timing-out classifier looked
exactly like a disabled one and cost one analysis its whole first hypothesis.
`llm_type_timeout_s` is deliberately tight — that call holds the ingest lock.

Each localization call ships the whole gazetteer enum (~3.5k input tokens,
~$0.004), so the question for a wasted call is always "could a deterministic
rule have known this for free?" — e.g. `resolve.py::in_promo_thread` vetoes
replies inside a fundraising thread by walking up the reply chain.

## Things that look like bugs but are decisions

Proposing to "fix" these is worse than useless — they were decided deliberately
and at least one was decided after a live failure.

- **Ballistics have no vector.** A ballistic descends on its own trajectory;
  several toponyms seconds apart are several targets, not one path. The
  enumeration split in `_handle_sighting` is ballistic-only for exactly this
  reason, and `ThreatLayer.tsx` refuses to draw a line for `kind='impact'`.
- **Impact locations are never published live.** Showing where strikes landed,
  while the raid is on, is damage assessment for whoever launched it. Impacts
  are withheld from the map, the feed, the banner and today's journal until the
  alert ends. See `tests/test_impact_privacy.py`.
- **A spotter's full "відбій" does not close everything.** Only the official
  channel can; a spotter's informal all-clear is premature often enough that it
  once closed a live attack. Type-scoped stand-downs are kept.
- **The app never replaces the official air-raid alert.** Nothing in an analysis
  should push it toward being an authoritative warning system.
- **Type inheritance is NOT gated on geography.** It looks like it should be:
  `_note_and_inherit_type` is channel+time only, and on the oblast-wide northern
  channel a type does smear across unrelated targets (08-20: 59% of that
  channel's events inherit, median 44 km from where the type was stated, up to
  103 km). Both obvious gates were measured against the corpus and both make
  things worse:
  - **distance threshold** — the dominant *legitimate* pattern is long-range.
    «Циркони. НІЖИН ПРОХОДЯТЬ» → «Жуляни увага!» is 125 km and correct; so are
    «Дві групи ракет на Ніжин» → Бориспіль/Бровари/Переяслав. A 45 km gate
    strips the type from exactly the approach warnings that matter most.
  - **implied-speed threshold** (distance ÷ elapsed vs. what the type can fly) —
    fails for a subtler reason worth remembering: **the timestamps measure how
    fast the spotter types, not how fast the target flies.** These channels warn
    districts *ahead* of the target, so the Ніжин→Жуляни pair reads as 125 km in
    36 seconds.

  The 08-20 case that motivated the idea («На Новгород-сіверський» typed
  `jet_drone` from a target 103 km away) turned out to be a *gazetteer* bug: its
  reply parent «БпЛА біля Рогівки» matched no district, produced no event, and
  so the reply had no track to join and fell back to channel context. Adding
  Рогівка fixed it — one track, typed `shahed` from its own parent. Look for the
  broken chain before reaching for the geometry.

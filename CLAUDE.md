# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Kyiv Live Radar — an unofficial, supplementary situational-awareness map that
visualizes aerial-threat reports (drones/missiles) over Kyiv, sourced from
volunteer-spotter Telegram channels. **It never replaces the official air-raid
alert.** Single-user MVP, not a public product.

See `WORKFLOW.md` for a detailed walkthrough (Ukrainian) of the full pipeline
with a maintained list of known weak points/false-positive classes — read it
before touching `app/parsing/rules.py` or `app/domain/tracking.py`.

## Commands

### Backend (`backend/`, Python 3.11+, FastAPI + async SQLAlchemy)

```bash
cd backend
# Name the version explicitly — a bare `python3` picks up macOS/Xcode's 3.9,
# which silently diverges from `.python-version`/Railway. The code uses 3.11+
# syntax that SQLAlchemy/Pydantic evaluate at RUNTIME (`X | None` in
# `Mapped[...]`, `datetime.UTC`), so an older venv fails at import, not at lint.
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt ruff
.venv/bin/uvicorn app.main:app --port 8137 --reload   # dev server

.venv/bin/pytest tests/ -q                             # full suite
.venv/bin/ruff check app tests eval scripts            # lint (config in pyproject.toml)

# `requirements.txt` starts with `-c constraints.txt`, so that one command pins
# every transitive version — CI, the Railway build and your venv all resolve the
# SAME set. This is not optional bookkeeping: anthropic 1.0 shipped mid-day on
# 2026-08-20, swapped httpx for httpx2, and broke `main` with no code change of
# ours. Upgrade DELIBERATELY (see the header of constraints.txt), never by
# letting a fresh resolve happen.
.venv/bin/pytest tests/test_tracking.py -q              # one file
.venv/bin/pytest tests/test_tracking.py::test_same_district_corroborates_into_one_track -q   # one test
```

Parser accuracy gate (hand-labeled golden set, `eval/eval_set.jsonl`):
```bash
.venv/bin/python eval/run_eval.py --verbose      # also runs as tests/test_eval.py
```

Target-type accuracy per tier (rules → channel window → LLM classifier), on the
same hand-labeled sessions; `--llm` costs ~$0.0017/message and asks before it
spends:
```bash
DATABASE_URL="sqlite+aiosqlite:///./eval_backfill.db" .venv/bin/python eval/type_eval.py [--llm --yes]
```

Track-level accuracy (does a real target end up as ONE track, not split/merged
— the thing that actually matters for the map): `eval/track_eval.py` against
`eval/ground_truth_sessions.json` (74 hand-labeled real target sessions from
871 real backfilled messages, no LLM):
```bash
DATABASE_URL="sqlite+aiosqlite:///./eval_backfill.db" .venv/bin/python eval/track_eval.py --verbose
```

Other eval/maintenance scripts (see each file's docstring for exact usage):
- `eval/mine_toponyms.py` / gap-analysis against `ground_truth_sessions.json` — find gazetteer coverage gaps.
- `eval/compare_llm.py` — rules vs. rules+LLM on real captured messages.
- `eval/backfill_once.py` — clean one-shot Telegram backfill into a DB for analysis (stop the live listener first, it holds the session).
- `scripts/reprocess_raw.py [--no-llm] [--limit N]` — replay ALL stored `raw_messages` through the CURRENT parser/gazetteer/tracking logic (e.g. after a parser fix) without re-fetching Telegram. **Destructive** (wipes `threats`/`threat_events`, not `raw_messages`) — stop the live backend first, test against a DB copy before running on the real one.
- `scripts/geocode_localities.py` — batch-geocode new gazetteer candidates via Nominatim.
- `scripts/dump_openapi.py` — write the OpenAPI schema to the repo-root `openapi.json` (see the type-contract section below).
- `app/telegram_login.py` — one-time interactive Telegram login. Plain (file session, local dev) or `--string` (prints a `TELEGRAM_SESSION_STRING` for ephemeral hosts like Railway — nothing written to disk).

### Frontend (`frontend/`, React + TS + Vite)

```bash
cd frontend
npm install
npm run dev       # http://localhost:5173, reads VITE_API_URL / VITE_WS_URL from frontend/.env
npm run build      # tsc -b && vite build — this IS the type-check step
npm run lint       # ESLint 9 flat config; react-hooks/exhaustive-deps is an error
npm run test       # Vitest, pure-logic suites only (no DOM) — src/**/*.test.ts
npm run gen:types  # regenerate src/api-types.ts from the repo-root openapi.json
```

### The frontend↔backend type contract

`frontend/src/types.ts` no longer hand-mirrors the Pydantic models — it aliases
generated types. **After changing any Pydantic schema, regenerate both ends**,
or CI fails on the up-to-date checks:

```bash
cd backend  && .venv/bin/python scripts/dump_openapi.py   # -> repo-root openapi.json
cd frontend && npm run gen:types                          # -> src/api-types.ts
```

Enum-like string fields must be a `Literal` for the generated types to narrow.
Declare each one ONCE in `app/models.py` as `Foo = Literal[...]` and derive its
runtime tuple with `FOOS = get_args(Foo)` — never write the two out separately.
Only the WebSocket envelope and the two `response_model`-less routes are still
typed by hand in `types.ts` (each says why).
```

## Architecture

### Ingestion pipeline (the core of the backend)

One entry point, `app/pipeline/ingest.py::ingest_message` (serialized behind a
single `asyncio.Lock` — concurrent messages are processed strictly sequentially
to avoid SQLite races splitting one track into two), shared by every feed
source. Pipeline: **store raw → parse (rules) → LLM fallback (maybe) → track →
fuse → broadcast**.

1. **Raw storage first** (`raw_messages` table) — even if parsing fails
   completely, the original text is kept for eval-set growth and reprocessing.
2. **Rule parser** (`app/parsing/rules.py`, vocab in `app/parsing/vocab.py`,
   district matching in `app/parsing/matcher.py`) — no NLP library, a
   hand-written regex/keyword parser over normalized text: target type →
   status → district matching (gazetteer-driven `DistrictMatcher`, stem-based
   so Троєщина/Троєщині/Троєщину all match one entry) → target count → a
   chain of message-level suppression filters (aftermath news, siren-only
   echoes, negation, day-recap softening — each is a curated word list, not
   NLP; extend these when a new false-positive pattern shows up in real
   data).
3. **LLM** (Claude Haiku 4.5) — three consumers, one budget guard
   (`llm_spend_ok`), all enum-railed by structured output so the model can
   never invent a value. Bearing/vector math is never delegated to the LLM.
   - `app/parsing/type_llm.py` — **target type from the recent feed**, the
     main consumer. 79% of localizable sightings state no type, and after the
     per-channel window and the incident prior 46% are still `unknown`. Gets
     the last 25 messages of ALL channels over 2h (measured: own-channel/30min
     types 3 of 25 cases, cross-channel/2h types 22 of 25). Runs LAST, so it
     can only fill an `unknown` — never overrule the rules. `llm_type_mode='live'`;
     `eval/type_eval.py` scores it (coverage 40.9% -> 65.1%, family accuracy
     93.7% -> 95.5%), and `'shadow'` re-audits a night without touching the map.
   - `app/pipeline/triage.py` — the async second pass (notices, axes, rescue).
   - `app/parsing/llm.py` localization — **off by default**
     (`llm_localize_enabled`): the gazetteer enum was 81% of the prompt's
     tokens and produced 3 inline events + 26 rescues for the life of the
     project. Coverage gaps are found by the admin queue in
     `app/api/coverage.py` instead — the gazetteer is the real lever, not the
     LLM. `pipeline.ingest.should_fallback` still gates what reaches the
     second pass.
4. **Track grouping** (`app/domain/tracking.py`) — the most failure-prone
   layer. Priority order: (a) Telegram reply-threading (a reply to an OPEN
   track's message joins that track — the strongest signal), (b)
   corroboration (a non-reply sighting joins an open track only if that
   track's **most recent** event was over the SAME district within
   `corroboration_window_minutes`), (c) otherwise start a new track.
   Deliberately NOT "continue the newest open track" — that collapsed
   independent targets into mega-track zigzags during busy alerts. The
   corroboration window and match-latest-only behavior were empirically
   tuned against `eval/track_eval.py`, not guessed.
5. **Fusion** (`app/domain/fusion.py`) — cross-source corroboration count
   (reposts of one original don't inflate it — dedup via `_origin_key`),
   conflict detection when sources disagree on target type, confidence score.
6. **Broadcast** (`app/pipeline/broadcast.py`) — fans out over
   `/ws/threats`; the frontend also polls `GET /threats/active` +
   `GET /events/recent` on load.

### Three interchangeable feed sources (`app/main.py` lifespan, priority order)

Selected by env vars, mutually exclusive:
1. `TELEGRAM_ENABLED=true` — real Telethon MTProto listener (`app/feeds/telegram.py`), reads-only, 3 configured channels (`TELEGRAM_CHANNELS`).
2. `REPLAY_REAL_DATA=true` — replays 871 real captured messages (`app/data/real_sample_messages.jsonl`) through the real pipeline (`app/feeds/replay.py`), preserving original reply chains and timestamps, for demoing real tracks/vectors without Telegram credentials.
3. `SIMULATOR_ENABLED=true` (default) — synthetic random routes through the real parser/tracker (`app/feeds/simulator.py`). Never reply-threads, so tracks never span 2+ districts — the map only ever shows dots, not vectors, in this mode.

### HTTP layer (`app/api/`, `app/schemas/`)

`api/routes.py` is only an assembler — it includes `api/public/` (unauthenticated
reads, one module per domain area) and `api/admin/` (every route gated by
`require_admin`). Helpers needed by more than one module live in `api/deps.py`.
`app/schemas/` mirrors the same split, with `__init__.py` re-exporting every
model so `from ..schemas import X` keeps working from anywhere. Add a new
endpoint to the module that owns its area, not to `routes.py`.

### Gazetteer (`app/gazetteer.py`)

112 entries: 10 administrative raions + in-city micro-neighborhoods/landmarks
+ approach-corridor villages, each with a stem + aliases the spotters
actually use. Grown reactively from real feed gaps — coverage is the primary
lever for both rule and LLM accuracy. **Watch for stem collisions** when
adding a short name: a district stem can accidentally match an unrelated
common word (e.g. "Остер" was dropped — its stem falsely matched
"остерігайтеся"=beware; "Щасливе" was kept only after an empirical
false-positive sweep against the real corpus, since it also means "happy").
Always geocode via `scripts/geocode_localities.py` and sweep the real corpus
before committing a new entry.

### Frontend code conventions (`frontend/src`)

- **Comments are the exception, not the default.** Prefer readable code —
  clear names for variables, functions, and files — over narrating what code
  does. Only write a comment for a genuinely non-obvious *why* (a hidden
  constraint, a workaround, a subtlety that would bite the next reader) — the
  existing comments in `store.ts`/`ThreatLog.tsx` are the bar to clear, not a
  license to add one per function.
- **Avoid `useEffect` wherever a direct alternative exists.** Prefer explicit,
  sequential code: event handlers, store actions that fetch-then-set inline
  (see `inspectThreat` in `store.ts`), values derived during render. Reach for
  `useEffect` only to synchronize with something genuinely outside React
  (subscriptions, timers, the DOM, browser APIs) — not to react to state
  changes that could just be computed inline.
- **One component, one file**, named after the component it exports
  (`ThreatLog.tsx` → `ThreatLog`). A small subcomponent that only exists to
  support one parent can live in that file *until* the parent needs
  decomposing anyway — then it moves out too. Don't use "it's just a helper"
  as an excuse to keep growing one file.
- **120 lines is the signal to decompose a component**, not a target to hit by
  cramming. Split by pulling out: pure helper functions (formatting,
  grouping/sorting) into a sibling `.ts` file; independent chunks of JSX into
  their own component; anything reusable into `lib/` or a hook. When a
  component outgrows one file, colocate the pieces it split into (a
  `ComponentName/` folder) rather than dumping helpers into a shared
  grab-bag `utils.ts`.
- **Import via an alias, not a `../../` chain.** Introduce a `@/` alias rooted
  at `src/` (`tsconfig.json` `compilerOptions.paths` + `vite.config.ts`
  `resolve.alias`) so imports read `@/store`, `@/theme`, `@/components/...`
  instead of counting `../` segments.

A few more that follow from the same instincts, worth applying as the
refactor touches each file:
- Keep async/data-fetching logic in Zustand store actions (as `inspectThreat`
  already does), not component-level effects — this is usually *why* a
  `useEffect` felt necessary in the first place.
- Select narrowly from the store (`useRadar((s) => s.log)`, already the
  convention) — never destructure the whole store — so an unrelated field
  changing doesn't re-render a component that doesn't use it.
- Prefer a discriminated union + exhaustive `if`/`switch` for anything
  variant-shaped (already how `WSMessage` is handled) — a new variant left
  unhandled should fail to compile, not fail silently at runtime.
- Pure logic (grouping, formatting, matching) belongs in a plain function
  with no JSX and no hooks — easy to unit-test, and it's usually the biggest
  chunk of a file blowing past 120 lines.

Several existing files (`ThreatLog.tsx`, `store.ts`) predate these rules and
are the intended first targets of the "точковий рефакторинг" — not a reason
to treat the rules as aspirational elsewhere.

### Deployment

Backend → Railway (`railpack.json` sets the uvicorn start command; Postgres
via `DATABASE_URL`, auto-normalized from Railway's plain `postgres://` scheme
to `postgresql+asyncpg://` in `config.py`). Frontend → Vercel, root directory
`frontend/`. The Telethon listener needs a persistent connection — not a
serverless function; on Railway's ephemeral filesystem use
`TELEGRAM_SESSION_STRING` (from `telegram_login.py --string`) instead of the
file-based local dev session.

### Releasing (changelog is mandatory)

**Every prod release MUST add a `CHANGELOG` entry** in
`frontend/src/changelog.ts` (`APP_VERSION` derives from the newest entry, shown
in-app at Settings → `/change-log`). The full release procedure — how to write
and version the entry, the rule that the changelog must not leak admin/internal
details to regular users, build verification, and the commit+push — lives in the
**`/do-release` skill** (`.claude/skills/do-release/SKILL.md`). Run `/do-release`
to cut a release; consult that skill before touching `changelog.ts` by hand.

### Analyzing a night of real messages

Feed accuracy work starts from an export, not from reading code: Адмінка → Весь
фід → Експорт produces the JSON, and the **`/analyze-feed` skill**
(`.claude/skills/analyze-feed/SKILL.md`) turns it into ranked findings and fixes.
Its `scripts/feed_report.py` does the mechanical pass (outcome histogram, LLM
spend split between the inline and triage paths, out-of-order ingestion, broken
reply chains, track fan-out) with plain `python3` and no venv;
`references/failure-taxonomy.md` maps each failure shape to the code that owns
it, and records the choices that must NOT be "fixed" (ballistics have no vector,
impact locations are never published live, a spotter's відбій doesn't close
everything).

### Working agreement — do NOT auto-commit or push

Make and verify changes locally (tests, `npm run build`, run the app), but do
**not** run `git commit` or `git push` on your own. The maintainer tests each
change locally first and then gives an explicit go-ahead ("пуш"/"комітимо")
before anything is committed or pushed. Prepare the diff and stop there; wait for
that signal.

The **one exception** is the `/do-release` skill: invoking it IS the explicit
go-ahead, so that skill (and only that skill) may commit and push on its own.

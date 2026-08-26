# Kyiv Live Radar

Auxiliary, **unofficial** situational-awareness layer that visualizes aerial-threat
reports over Kyiv on a live map. Deployed (backend on Railway, frontend on
Vercel) and reading real Telegram spotter channels through a rule-based parser
with an LLM fallback; a synthetic simulator and a real-data replay mode are both
available as feed sources when Telegram credentials aren't configured (see
"Enable the real Telegram feed" below).

> ⚠️ This is a supplementary service. Data is manual text from volunteer spotters,
> district-level accuracy, seconds-to-minutes delay. It **never** replaces the
> official air-raid alert. Always act on the siren and official apps.

`CLAUDE.md` is the working guide for the codebase (commands, architecture,
conventions). `WORKFLOW.md` walks one message through the whole pipeline in
Ukrainian and keeps the list of known weak points — read it before touching
`app/parsing/rules.py` or `app/domain/tracking.py`.

## What works today

### Backend (`backend/`, FastAPI + async SQLAlchemy; SQLite locally, Postgres on Railway)

**Ingestion** — one entry point, `app/pipeline/ingest/`, serialized behind a
single lock so concurrent messages can't split one track in two:
store raw → parse (rules) → LLM fallback (maybe) → track → fuse → broadcast.

- `app/parsing/` — the parser. No NLP library: a hand-written regex/keyword
  chain (`rules.py`, vocabulary in `vocab.py`, stem-based district matching in
  `matcher.py`) producing target type, status, districts, counts, and a set of
  message-level suppression flags.
- `app/gazetteer.py` — 229 entries: administrative raions, in-city
  micro-neighbourhoods/landmarks, and approach-corridor localities, each with a
  stem plus the aliases spotters actually use.
- `app/domain/` — the reasoning layer: `tracking.py` (group events into target
  tracks), `fusion.py` (cross-source corroboration, repost dedup, conflict
  detection), `incidents.py` + `attack.py` (one alert = one incident, and its
  classification), `alerts.py` (the official air-raid alert), `axes.py`
  (directional threat wedges), `staleness.py`, `home_danger.py`, `journal.py`,
  `analytics.py`.
- `app/feeds/` — three interchangeable sources: `telegram.py` (Telethon MTProto
  listener, read-only), `replay.py` (871 real captured messages with their
  original reply chains and timestamps), `simulator.py` (synthetic routes through
  the real parser). Plus `alert_zones.py`, the raion-level siren layer.
- `app/pipeline/` — `triage.py` (async second-pass LLM), `sweeper.py` (retire
  silent tracks), `broadcast.py` (WS fan-out), `home_push.py` /`webpush.py` /
  `contact_push.py` (Web Push), `reprocess.py` (replay stored raw messages
  through the current parser), `keepalive.py`.
- `app/api/` — 59 routes, split into `public/` (unauthenticated reads) and
  `admin/` (every route behind `require_admin`). `app/auth/` covers accounts and
  SSO. `app/schemas/` mirrors the same split and is the source of the generated
  frontend types.
- **Regions**: the radar watches more than one pool. `kyiv` (city + oblast) and
  `chernihiv` (the northern early-warning approach) have separate track
  populations that never corroborate, continue or close each other.
- **Migrations**: Alembic, 29 revisions, applied on boot.
- **Tests**: `pytest tests/` — 660 tests, all green, plus a hand-labeled parser
  accuracy gate (see below) that runs as part of the suite.

### Frontend (`frontend/`, React + TS + Vite, react-leaflet, Zustand, i18n)

- **Live map**: track tails and direction arrows (deterministic bearing), per-type
  glyphs, staleness fade against a server-owned `stale_at`, impact markers,
  city-wide pulse, directional axis wedges, raion siren layer, home zone with a
  danger indication.
- **Feed** with attack-summary cards, notices and day separators.
- **Journal** (`/journal`) — a per-day calendar of attacks/targets/types/alert
  duration, plus an across-days statistics tab.
- **Admin console** (`/admin`) — manual parser overrides (dismiss/restore/retype,
  edit or delete a sighting), the full raw-message feed with export, coverage
  gaps, harvested corrections, source management, bug reports, and a preview +
  apply reprocess.
- **Accounts** — email/password, Google and Telegram SSO; contacts with shared
  home markers; opt-in collectible cards; Web Push notifications; installable PWA.
- Permanent safety disclaimer, UK/EN switch, in-app changelog.

## The frontend↔backend type contract

`frontend/src/types.ts` aliases types generated from the repo-root
`openapi.json`. After changing any Pydantic schema, regenerate both ends or CI
fails:

```bash
cd backend  && .venv/bin/python scripts/dump_openapi.py   # -> repo-root openapi.json
cd frontend && npm run gen:types                          # -> src/api-types.ts
```

The WebSocket envelope is the one hand-written mirror (FastAPI documents only
HTTP routes). It is a discriminated union with an exhaustive switch, so a frame
added on the backend and forgotten on the frontend fails the build.

## Parser eval

The parser is measured against a hand-labeled golden set (`eval/eval_set.jsonl`).
Ground-truth labels are what a human considers correct — the harness reports
where the parser diverges.

```bash
cd backend
.venv/bin/python eval/run_eval.py --verbose   # report + mismatches
.venv/bin/pytest tests/test_eval.py           # same, as a gated test
```

Metrics: target-type / status / new-target accuracy, and district
**precision/recall** (recall is the strictest threshold — a missed district is a
missed sighting). The harness gates via thresholds in `run_eval.py`.

**Grow the set from real data** — a hand-authored set mostly guards against
regressions; real accuracy comes from real phrasing:

```bash
.venv/bin/python eval/export_from_raw.py --limit 200 > eval/to_label.jsonl
# correct the pre-filled labels, then append good rows to eval/eval_set.jsonl
```

**Grow the gazetteer from real data.** Recall is bounded by district coverage,
not parser logic. `eval/mine_toponyms.py` pulls channel history, runs the parser,
and ranks the place-names it could NOT localize — the work-list for new gazetteer
entries. Always geocode via `scripts/geocode_localities.py` and sweep the real
corpus for stem collisions before committing an entry.

```bash
.venv/bin/python eval/mine_toponyms.py --limit 300
```

The admin console's **Прогалини** tab does the same scan live, so a coverage gap
is visible without running anything.

## Track-level eval

Per-message field accuracy doesn't measure whether the TRACKING layer groups
messages into the right real-world targets — the thing that actually drives the
map. `eval/ground_truth_sessions.json` hand-labels 74 real target sessions from
871 real backfilled messages. `eval/track_eval.py` compares the pipeline's actual
groupings against it: session purity (1 real target → 1 track?), track purity
(1 track → only 1 real target — the mega-track check), and vector accuracy.

```bash
DATABASE_URL="sqlite+aiosqlite:///./eval_backfill.db" .venv/bin/python eval/track_eval.py --verbose
```

It exits non-zero when a metric falls below the floors recorded at the top of the
script, and `tests/test_track_eval.py` asserts on that — **but only when
`eval_backfill.db` is present**, and skips otherwise. That is deliberate: per the
`_meta` block in `ground_truth_sessions.json` the DB is built from a live Telegram
backfill of a moving window, so it cannot be rebuilt in CI. The gate runs where
the data lives.

## LLM layers (Claude Haiku 4.5)

Rules stay the primary layer. The LLM is used twice, both times for **entity
extraction and classification only** — never bearing/ETA math:

1. **Inline fallback** (`app/parsing/llm.py`) — when the rules find no district on
   a threat-flavoured message and it isn't obviously about another oblast
   (`pipeline.ingest.should_fallback` gates this to avoid paying for calls known
   to come back empty).
2. **Async triage** (`app/pipeline/triage.py`) — a second pass over messages the
   rules suppressed or couldn't localize, off the critical path. It can confirm a
   suppression, surface a directional/forecast/status notice, or (behind a flag)
   rescue a wrongly-suppressed threat at its original timestamp.

Safety rails:

- Structured output constrains districts to an **enum of known gazetteer ids** —
  the model cannot invent a location. `target_type`/`status` are enum-railed too,
  and re-validated in Python before anything reaches the DB.
- The prompt disambiguates other cities/oblasts (Дніпро the city vs Kyiv's
  Дніпровський raion, Харків, Запоріжжя, …) → returns empty.
- A timeout (`LLM_TIMEOUT_S`, default 5s) or any error falls back to the
  rule-based result.
- The LLM **never** declares `clear`/`destroyed` and never closes a track — those
  belong to the rules and to the official alert channel.
- Daily/monthly spend caps (`llm_spend_ok`) measured by when the call was BILLED,
  so a backfill or a reprocess counts against today's budget.
- Each event records `decision_source` = `rule` | `llm` | `triage` | `sim`.

Enable with `ANTHROPIC_API_KEY` set and `LLM_FALLBACK_ENABLED=true` (default).
Compare rules vs. rules+LLM on real captured messages:

```bash
.venv/bin/python eval/compare_llm.py --limit 15
```

Measured against real messages, the LLM localizes only ~5% of the rule-misses —
most misses are genuinely unlocalizable (other oblasts, news/commentary, or real
Kyiv-area places simply missing from the gazetteer, which the enum-constrained
model can't invent either). **The real coverage lever is gazetteer size, not the
LLM.**

## District boundaries

The 10 administrative raions render as real **OSM boundary polygons** (fetched
once via `scripts/fetch_boundaries.py` → Nominatim, Ramer-Douglas-Peucker
simplified, committed to `app/data/boundaries.json`, seeded into `districts`).
Representative lat/lon for those raions is the polygon centroid. Microdistricts
and approach-corridor towns stay as points (no crisp official boundary).

- `GET /districts/boundaries` serves the geometries (kept out of `/districts`).
- The frontend draws them as a subtle base layer and uses point-in-polygon to
  show which raion the home location falls in.
- We deliberately do **not** draw fake circles around microdistrict centroids —
  that would imply precision the data doesn't have.

## Not yet built / known gaps

- Nearest-edge distance to the home raion for ETA (currently centroid bearing).
- Richer fusion (time-windowed correlation, trust-weighting, entity resolution).
- A reply thread that narratively covers several physical targets still groups
  them as one — the hardest open tracking problem (see WORKFLOW.md §4).
- No human review step anywhere in the pipeline; the admin console is a
  correction tool AFTER the fact, not a gate before publication.

## Enable the real Telegram feed

1. Get `api_id` / `api_hash` from https://my.telegram.org.
2. Create the login session once (interactive — prompts for phone + code):
   ```bash
   cd backend
   TELEGRAM_API_ID=... TELEGRAM_API_HASH=... .venv/bin/python -m app.telegram_login
   ```
   On a host with no persistent local disk (Railway), use `--string` instead
   — it prints a `TELEGRAM_SESSION_STRING` to paste into an env var rather
   than writing a session file:
   ```bash
   TELEGRAM_API_ID=... TELEGRAM_API_HASH=... .venv/bin/python -m app.telegram_login --string
   ```
3. Configure `backend/.env` (or the host's env vars) and restart the API:
   ```
   TELEGRAM_ENABLED=true
   TELEGRAM_API_ID=...
   TELEGRAM_API_HASH=...
   SIMULATOR_ENABLED=false
   # TELEGRAM_SESSION_STRING=...   # only if using --string above
   ```
   The **channel list lives in the database**, not in env: the active rows in
   `sources` ARE the live subscription, managed from Адмінка → Джерела, and a
   change there makes the listener reconnect and re-subscribe. `TELEGRAM_CHANNELS`
   only seeds an empty table on first boot. (Reads only; respect Telegram ToS.)
   Each login (file or string) is an independent Telegram session — running this
   twice for two different environments doesn't invalidate either.

## Run locally

Backend (**Python 3.11+ required** — the code uses 3.11 syntax that SQLAlchemy and
Pydantic evaluate at runtime, so an older venv fails at import, not at lint; a
bare `python3` picks up macOS/Xcode's 3.9):

```bash
cd backend
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt ruff
.venv/bin/uvicorn app.main:app --port 8137 --reload
```

`requirements.txt` starts with `-c constraints.txt`, so that one command pins
every transitive version — CI, the Railway build and your venv all resolve the
same set. Upgrade deliberately (see the header of `constraints.txt`); letting a
fresh resolve happen is how `anthropic 1.0` silently swapped `httpx` for `httpx2`
and broke `main` on 2026-08-20.

Frontend:

```bash
cd frontend
npm install
npm run dev     # http://localhost:5173
npm run build   # tsc -b && vite build — this IS the type-check step
```

The frontend reads `VITE_API_URL` / `VITE_WS_URL` from `frontend/.env`, plus
`VITE_CARTO_KEY` — a free CARTO basemap key (5M tiles/month, requested at
[carto.com/basemaps/apikey](https://carto.com/basemaps/apikey)). CARTO no longer
serves its raster basemaps anonymously: without the key every tile arrives with
an "API KEY REQUIRED" watermark burned into the PNG by their CDN. The map still
works unkeyed, so the variable is optional locally, but production needs it set
in Vercel too.

## Deployment

- **Frontend** → Vercel, root directory `frontend` (static Vite build).
- **Backend** → Railway, root directory `backend`, single always-on service +
  a Postgres plugin (`DATABASE_URL` auto-injected in libpq scheme, rewritten
  to `postgresql+asyncpg://` in `config.py`). Start command comes from
  `railpack.json` (not a Procfile), which installs straight from
  `requirements.txt` — so a version cap has to live there to protect prod.
  The Telethon listener runs in-process (`TELEGRAM_ENABLED=true`) — it needs a
  persistent MTProto connection, not a serverless task, so it can't live on
  Vercel. `app/worker.py` sketches an alternative two-service split (separate
  `api`/`worker` processes) for if the in-process model needs to scale later;
  not currently deployed that way.
- Railway's filesystem is ephemeral, so the Telegram session can't be a local
  file there — use `TELEGRAM_SESSION_STRING` (see "Enable the real Telegram
  feed" above) instead of the file-based session local dev uses.
- **Releases** always add a `CHANGELOG` entry in `frontend/src/changelog.ts`
  (`APP_VERSION` derives from the newest one). Run the `/do-release` skill rather
  than editing it by hand.

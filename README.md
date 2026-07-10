# Kyiv Live Radar

Auxiliary, **unofficial** situational-awareness layer that visualizes aerial-threat
reports over Kyiv on a live map. Deployed (backend on Railway, frontend on
Vercel) and reading 3 real Telegram channels through a rule-based parser with
an LLM fallback; a synthetic simulator and a real-data replay mode are both
available as feed sources when Telegram credentials aren't configured (see
"Enable the real Telegram feed" below).

> ⚠️ This is a supplementary service. Data is manual text from volunteer spotters,
> district-level accuracy, seconds-to-minutes delay. It **never** replaces the
> official air-raid alert. Always act on the siren and official apps.

## What works today

- **Backend** (FastAPI + async SQLAlchemy, SQLite locally):
  - `districts` gazetteer (Kyiv raions + microdistricts, seeded).
  - `sources` registry — the app is **multi-source aware**: events carry a
    source and a repost-origin id.
  - `raw_messages` — every incoming message stored verbatim before parsing
    (first-hand data, eval sets, reprocessing).
  - `threats` / `threat_events` data model.
  - **Rule-based parser** (`app/parser.py`): target type, status, and district
    matching (regex + gazetteer + a light Ukrainian stemmer for case forms).
  - **Track builder** (`app/tracking.py`): groups events into tracks, continues
    vs. starts-new by new-target markers and a time-gap threshold (spec §5.4).
  - **Ingest pipeline** (`app/ingest.py`): the single entry point (store → parse
    → track → fuse → broadcast) shared by Telegram and the simulator.
  - **Fusion layer** (`app/fusion.py`): cross-source corroboration, repost
    dedup (reposts of one original don't inflate confidence), and conflict
    detection when sources disagree.
  - **Telegram listener** (`app/telegram_listener.py`, Telethon) — reads
    configured public channels into the pipeline. Off until credentials are set.
  - REST: `GET /districts`, `GET /threats/active`, `GET /threats/{id}/events`.
  - `WS /ws/threats` real-time broadcast.
  - **Text simulator** (`app/simulator.py`): emits realistic Ukrainian messages
    through the REAL parser/tracker so the frontend has live data before
    Telegram credentials exist. Toggle with `SIMULATOR_ENABLED`. Synthetic
    routes never reply-thread, so tracks never span 2+ districts — dots, not
    vectors.
  - **Real-data replay** (`app/replay.py`, `REPLAY_REAL_DATA=true`): replays
    871 real messages backfilled from all 3 channels, preserving their
    original reply chains and timestamps — for demoing real tracks/vectors
    without live Telegram credentials. Takes priority over the simulator.
  - **Tests**: `pytest tests/` — 58 tests, all green (parser, ingest/tracking/
    fusion, replay dataset sanity, LLM-fallback routing).
- **Frontend** (React + TS + Vite, react-leaflet, Zustand, i18n):
  - Live map: track tail, direction arrow (deterministic bearing), status colors.
  - Multi-source signals surfaced: corroboration count, confidence %, conflict flag.
  - Event feed, legend, home/radius layer (placeholder location).
  - Permanent safety disclaimer, UK/EN language switch.

## Parser eval

The parser is measured against a hand-labeled golden set (`eval/eval_set.jsonl`).
Ground-truth labels are what a human considers correct — the harness reports
where the parser diverges.

```bash
cd backend
.venv/bin/python eval/run_eval.py --verbose   # report + mismatches
.venv/bin/python -m pytest tests/test_eval.py # same, as a gated test
```

Metrics: target-type / status / new-target accuracy, and district
**precision/recall** (recall is the strictest threshold — a missed district is a
missed sighting). The harness gates via thresholds in `run_eval.py`.

**Grow the set from real data** (the point of spec §8.11 — a hand-authored set
mostly guards against regressions; real accuracy comes from real phrasing):

```bash
.venv/bin/python eval/export_from_raw.py --limit 200 > eval/to_label.jsonl
# correct the pre-filled labels, then append good rows to eval/eval_set.jsonl
```

**Grow the gazetteer from real data.** Recall is bounded by district coverage,
not parser logic. `eval/mine_toponyms.py` pulls channel history, runs the parser,
and ranks the place-names it could NOT localize — the work-list for new gazetteer
entries. Add Kyiv-area / approach-corridor localities (skip other oblasts).
Requires the Telegram session; stop the live listener first (it holds the lock).

```bash
.venv/bin/python eval/mine_toponyms.py --limit 300
```

## LLM fallback parser (Claude Haiku 4.5)

Rules stay the primary layer. When they can't localize a threat-flavored message
(`ingest._should_fallback`), the text is routed to Claude Haiku 4.5 for **entity
extraction only** — never bearing/ETA math. Safety rails:

- Structured output constrains districts to an **enum of known ids** — the model
  cannot invent a location.
- The prompt disambiguates other cities/oblasts (Дніпро the city vs Kyiv's
  Дніпровський district, Харків, Запоріжжя, …) → returns empty.
- A timeout (`LLM_TIMEOUT_S`, default 5s) or any error falls back to the
  rule-based result — the LLM is never on the critical path.
- Each event records `decision_source` = `rule` | `llm` for audit.

Enable with `ANTHROPIC_API_KEY` set and `LLM_FALLBACK_ENABLED=true` (default).
Compare rules vs. rules+LLM on real captured messages (spec §9.5):

```bash
.venv/bin/python eval/compare_llm.py --limit 15
```

Measured against real captured messages, the LLM localizes only ~5% of the
rule-misses — most misses are genuinely unlocalizable (other oblasts, news/
commentary, or real Kyiv-area places simply missing from the gazetteer, which
the enum-constrained LLM can't invent either). The real coverage lever is
gazetteer size, not the LLM — see `eval/ground_truth_sessions.json` for a
gap-analysis workflow. A rule-layer pre-filter (`ingest._OTHER_OBLAST`) skips
the LLM call outright for messages that only name another oblast/border
region, cutting call volume ~20% with no coverage loss.

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

## Track-level eval

Per-message field accuracy (above) doesn't measure whether the TRACKING layer
groups messages into the right real-world targets — the thing that actually
drives the map. `eval/ground_truth_sessions.json` hand-labels 74 real target
sessions from 871 real backfilled messages (all 3 channels, close-read for
reply-chain/content/timing justification). `eval/track_eval.py` compares the
pipeline's actual track groupings against it: session purity (1 real target →
1 track?), track purity (1 track → only 1 real target — the mega-track
check), and vector accuracy (does a real multi-district target's track
actually span 2+ districts?).

```bash
DATABASE_URL="sqlite+aiosqlite:///./eval_backfill.db" .venv/bin/python eval/track_eval.py --verbose
```

## Not yet built (next phases)

- Nearest-edge distance to the home raion for ETA (currently centroid bearing).
- Richer fusion (time-windowed correlation, trust-weighting, entity resolution).
- Notifications — intentionally out of scope for this MVP.
- Automated reconnect / health-check for the Telethon listener — currently a
  connection drop kills the background listener task silently; the API keeps
  serving stale data with no visible error outside the raw log.

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
   TELEGRAM_CHANNELS=channel_one,channel_two   # usernames without @
   SIMULATOR_ENABLED=false
   # TELEGRAM_SESSION_STRING=...               # only if using --string above
   ```
   With `TELEGRAM_ENABLED=true` and channels set, the API runs the listener
   instead of the simulator. (Reads only; respect Telegram ToS — spec §12.)
   Each login (file or string) is an independent Telegram session — running
   this twice for two different environments doesn't invalidate either.

## Run locally

Backend (Python 3.11+ recommended; 3.9 works for the skeleton):

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8137
```

Frontend:

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

The frontend reads `VITE_API_URL` / `VITE_WS_URL` from `frontend/.env`.

## Deployment

- **Frontend** → Vercel, root directory `frontend` (static Vite build).
- **Backend** → Railway, root directory `backend`, single always-on service +
  a Postgres plugin (`DATABASE_URL` auto-injected in libpq scheme, rewritten
  to `postgresql+asyncpg://` in `config.py`). Start command comes from
  `railpack.json` (not a Procfile). The Telethon listener runs in-process
  (`TELEGRAM_ENABLED=true`) — it needs a persistent MTProto connection, not a
  serverless task, so it can't live on Vercel. `app/worker.py` sketches an
  alternative two-service split (separate `api`/`worker` processes) for if
  the in-process model needs to scale later; not currently deployed that way.
- Railway's filesystem is ephemeral, so the Telegram session can't be a local
  file there — use `TELEGRAM_SESSION_STRING` (see "Enable the real Telegram
  feed" below) instead of the file-based session `TELEGRAM_ENABLED` normally
  expects for local dev.

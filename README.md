# Kyiv Live Radar

Auxiliary, **unofficial** situational-awareness layer that visualizes aerial-threat
reports over Kyiv on a live map. This repo currently contains the **working
skeleton** (vertical slice) described below — the real Telegram feed and parser
are stubbed behind a synthetic simulator.

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
    Telegram credentials exist. Toggle with `SIMULATOR_ENABLED`.
  - **Tests**: `pytest` — parser (12) + ingest/tracking/fusion (8), all green.
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

On the current live feed the LLM localizes ~13% of the rule-misses (declensions
the stemmer misses, districts named in prose) with **zero** out-of-area false
positives after prompt hardening.

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

## Not yet built (next phases)

- Nearest-edge distance to the home raion for ETA (currently centroid bearing).
- Richer fusion (time-windowed correlation, trust-weighting, entity resolution).
- Notifications — intentionally out of scope for this MVP.

## Enable the real Telegram feed

1. Get `api_id` / `api_hash` from.
2. Create the login session once (interactive — prompts for phone + code):
   ```bash
   cd backend
   TELEGRAM_API_ID=... TELEGRAM_API_HASH=... .venv/bin/python -m app.telegram_login
   ```
3. Configure `backend/.env` and restart the API:
   ```
   TELEGRAM_ENABLED=true
   TELEGRAM_API_ID=...
   TELEGRAM_API_HASH=...
   TELEGRAM_CHANNELS=channel_one,channel_two   # usernames without @
   SIMULATOR_ENABLED=false
   ```
   With `TELEGRAM_ENABLED=true` and channels set, the API runs the listener
   instead of the simulator. (Reads only; respect Telegram ToS — spec §12.)

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

## Deployment (per spec)

- Frontend → Vercel (static). Backend → Railway (two always-on services: `api`
  and `worker`, shared Postgres). The Telethon listener needs a persistent
  MTProto connection — not a serverless task.

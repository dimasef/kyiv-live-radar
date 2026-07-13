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
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8137 --reload   # dev server

.venv/bin/pytest tests/ -q                             # full suite
.venv/bin/pytest tests/test_tracking.py -q              # one file
.venv/bin/pytest tests/test_tracking.py::test_same_district_corroborates_into_one_track -q   # one test
```

Parser accuracy gate (hand-labeled golden set, `eval/eval_set.jsonl`):
```bash
.venv/bin/python eval/run_eval.py --verbose      # also runs as tests/test_eval.py
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
- `app/telegram_login.py` — one-time interactive Telegram login. Plain (file session, local dev) or `--string` (prints a `TELEGRAM_SESSION_STRING` for ephemeral hosts like Railway — nothing written to disk).

### Frontend (`frontend/`, React + TS + Vite)

```bash
cd frontend
npm install
npm run dev       # http://localhost:5173, reads VITE_API_URL / VITE_WS_URL from frontend/.env
npm run build      # tsc -b && vite build — this IS the type-check step, no separate lint command
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
3. **LLM fallback** (`app/parsing/llm.py`, Claude Haiku 4.5) — only when
   rules found no district on a threat-flavored message AND it isn't
   obviously about another oblast (`pipeline.ingest.should_fallback` gates
   this to avoid paying for calls known to return empty). Structured output
   constrains `district_ids` to an **enum of known gazetteer ids** — the
   model cannot invent a location. Bearing/vector math is never delegated to
   the LLM. ~5% hit rate on rule-misses (measured) — the real coverage lever
   is the gazetteer, not the LLM.
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
`frontend/src/changelog.ts` — `APP_VERSION` is derived from the newest entry and
shown in-app (Settings → version history at `/change-log`). Do not ship a
user-visible change to prod without one. Each entry requires a `date`
(`YYYY-MM-DD`, the release day) and a `kind` per `SEMVER_RULES`: `patch` =
fix/tweak with no new capability (parser/gazetteer fixes, dedup, cosmetics),
`minor` = new operator-visible capability, `major` = public/breaking (stays 0
during the MVP). Bump the version accordingly, newest entry first. Write
`changes` in Ukrainian, operator-facing (what they'll notice), not internal
mechanics.

### Working agreement — do NOT auto-commit or push

Make and verify changes locally (tests, `npm run build`, run the app), but do
**not** run `git commit` or `git push` on your own. The maintainer tests each
change locally first and then gives an explicit go-ahead ("пуш"/"комітимо")
before anything is committed or pushed. Prepare the diff and stop there; wait for
that signal.

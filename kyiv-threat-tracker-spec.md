# Technical Specification: Kyiv Aerial Threat Tracker (MVP)

## 1. Context and goal

The system reads a public Telegram channel that monitors aerial activity (text posts about shahed drones, missiles, and other UAVs moving across districts), parses mentions of Kyiv districts, builds a target's track over time, and displays it in real time on a city map with an estimated direction of movement. The goal is an auxiliary layer of situational awareness for a specific person: is the tracked target approaching their district or not.

**Important (bake this into the product, not just the docs):** this is a supplementary, unofficial service. The source is manual text reports from volunteer spotters, accuracy is at the district level, with a delay of seconds to minutes. The product must never present "the vector isn't heading your way" as a reason to ignore the official siren or alerts.in.ua. The disclaimer must be visible in the UI at all times, not just during onboarding.

## 2. Technology stack

### Backend
- **Python 3.11+**
- **Telethon** — MTProto client for reading the public channel (requires your own `api_id`/`api_hash` from my.telegram.org)
- **FastAPI** — REST + WebSocket API
- **PostgreSQL** + **SQLAlchemy 2.0 (async)** + **Alembic** for migrations (SQLite is fine for local MVP development)
- **Redis** — pub/sub for broadcasting between WS instances (can be skipped for MVP with a single instance)
- **asyncio background worker** — a separate process that listens to the channel via Telethon events and writes to the DB
- **pymorphy3** (optional) — normalizes Ukrainian word forms of district names for fuzzy matching

### Frontend
- **React + TypeScript (Vite)**
- **react-leaflet** (Leaflet.js) — map, OSM tiles, free
- **native WebSocket** — real-time updates
- **Zustand** — lightweight state management
- **TailwindCSS** — styling

### Deployment
- **Docker Compose**: backend, telegram-worker, postgres, redis (optional), frontend, nginx as reverse proxy

## 3. Architecture

```
Telegram channel (public)
      │  Telethon events
      ▼
Telegram Listener (worker)
      │  raw message + timestamp
      ▼
Parser (regex + gazetteer + status rules)
      │  structured event {district, status, type, confidence}
      ▼
Track Builder (groups events into a single target track)
      │
      ▼
PostgreSQL  ──────────────►  REST API (history)
      │
      ▼
WebSocket broadcaster  ──►  Frontend (map, log, vector, ETA)
```

## 4. Data model

```sql
-- Gazetteer of Kyiv districts
districts (
  id, name, aliases text[], lat, lon, city
)

-- A single target's track (from first sighting to "destroyed"/lost)
threats (
  id, created_at, target_type,  -- 'shahed' | 'jet_drone' | 'missile' | 'unknown'
  status,                        -- 'unconfirmed' | 'tracking' | 'destroyed' | 'lost'
  closed_at
)

-- A single sighting within a track
threat_events (
  id, threat_id, district_id, raw_text, source_message_id,
  event_time, confidence  -- 0..1, lower for ambiguous mentions
)

-- User alert configuration
user_alert_config (
  id, user_id, home_lat, home_lon, radius_km, channel  -- 'push' | 'telegram' | 'email'
)
```

## 5. Parsing business logic (the product's core)

1. **Target type** — keywords: "shahed"/"moped" → shahed (~170–180 km/h by default); "jet-powered UAV" → jet_drone (~500–600 km/h); "missile"/"ballistic"/"glide bomb" → missile (separate branch, significantly higher speed, calculate ETA carefully — reaction time is critically short).
2. **Status** — emoji 🔴 → confirmed, 🟢 → all-clear/close track, keyword "destroyed"/"neutralized" → destroyed (close the track), "all-clear" → clear (close all active tracks citywide), "unconfirmed"/"not yet confirmed" → unconfirmed (low confidence, separate disabled style on the map).
3. **District matching** — lookup via the `aliases` dictionary (account for known spelling variants/abbreviations, e.g. "Troya" = Troieshchyna; for an ambiguous label with no confident match, keep it as-is rather than inventing an interpretation).
4. **Grouping into a track** — if there is an active track and the message doesn't contain a phrase like "new target"/"another one", treat it as a continuation of the existing track; start a new track on an explicit mention of a new target, or if more than N minutes have passed since the last sighting (configurable threshold, starting at 15).
5. **Vector and ETA** — using the last two sightings, compute a bearing, and, based on the target type's speed, an approximate ETA to the user's location if it lies within a ±X° sector of the vector. Deliberately avoid false precision here — show a range, not a single number.

## 6. API

```
GET  /districts
GET  /threats/active
GET  /threats/{id}/events
POST /users/alert-config
WS   /ws/threats          # broadcasts new threat_events and status changes
```

## 7. Frontend — core logic
- Map: marker on the district, a track "tail" (polyline), a direction arrow, colors by status (confirmed/unconfirmed/destroyed/clear).
- User's home location + radius — a separate layer.
- Browser push notification if an active track's vector intersects the user's radius within the estimated ETA.
- A permanently visible disclaimer and links to official sources (alerts.in.ua, the "Air Alert" app).

## 8. Step-by-step MVP implementation plan

1. **Gazetteer** — build a table of Kyiv districts/microdistricts with coordinates (can be extracted from OSM boundaries), seed the DB.
2. **Telegram listener** — a Telethon script that connects to the channel and simply stores raw messages with timestamps in the DB (no parsing yet).
3. **Parser** — a separate module, rule-based (regex + dictionary), covered by unit tests on real examples from the channel.
4. **DB schema + Alembic migrations**, REST endpoints (read-only at first).
5. **Track builder** — the logic for grouping events into a track (see 5.4).
6. **WebSocket broadcast** of new events to subscribers.
7. **Frontend: map** — react-leaflet, static rendering of historical tracks from the DB.
8. **Frontend: realtime** — WS connection, movement animation, vector.
9. **Alert config + ETA calculation + browser push**.
10. **Docker Compose deployment**, basic logging/monitoring (e.g. Sentry for parser errors).
11. **Accuracy iteration** on the live channel feed — the MVP's main risk; build in a manual review cycle for parsing errors before trusting the output for notifications.

## 9. AI fallback for parsing (optional enhancement)

The rule-based parser (section 5) remains the primary layer — cheap, instant, no network calls. The LLM is only invoked as a fallback when confidence is low:

1. The regex+dictionary parser tries to recognize the district/status/target type as usual.
2. If a district isn't found in `districts.aliases`, or the phrasing is ambiguous (multiple possible readings, a new phrasing, several targets mentioned in one message) — the text is routed to the LLM fallback.
3. Call the Claude API (model **Claude Haiku 4.5** — a classification/extraction task, doesn't need heavy reasoning, and speed is critical) with a short prompt: the raw text + a list of known districts + a strict **structured output / tool use** schema, with no free-form text in the response:
   ```json
   {"district_id": "...", "confidence": 0.0-1.0, "target_type": "shahed|jet_drone|missile|unknown", "is_new_target": bool, "status": "unconfirmed|confirmed|destroyed|clear"}
   ```
4. **Important:** the LLM is used only for entity extraction from text. The bearing and ETA calculations remain deterministic code, not the LLM — for a safety-critical calculation, trusting model generation isn't acceptable.
5. Before trusting the LLM output for notifications (rather than just logs), build an eval set of ~50–100 real messages from the channel and compare rule-based vs LLM accuracy.

Claude API docs (tool use / structured outputs, limits, pricing): https://docs.claude.com/en/docs/build-with-claude/tool-use

## 10. Deployment: Vercel (frontend) + Railway (backend)

- **Frontend → Vercel.** React/Vite static assets over a CDN, a standard flow, no extra configuration needed.
- **Backend → Railway, not Vercel.** Vercel functions are serverless with an execution-time limit and no persistent connection. The Telethon listener needs to hold a persistent MTProto connection to Telegram around the clock — that's fundamentally not a serverless task. On Railway, run two always-on services:
  - **api** — FastAPI + WebSocket endpoint, accepts connections from the frontend;
  - **worker** — Telethon listener + parser, writes to the shared DB (accepts no external requests).
  - Both connect to Railway Postgres (managed addon).
- The frontend on Vercel connects to the WS directly on the Railway domain (`wss://<app>.up.railway.app/ws/threats`) — serverless limits don't apply here since the connection bypasses Vercel functions and goes straight to Railway.
- **CORS**: allow the Vercel domain in FastAPI (`CORSMiddleware`, `allow_origins` from an env variable, not a wildcard in production).
- **Env variables** (set separately on Railway and Vercel, never hardcoded): `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `DATABASE_URL`, `ANTHROPIC_API_KEY`, `NEXT_PUBLIC_WS_URL` (or the Vite equivalent).

## 11. Multi-language support (i18n): Ukrainian + English

The product supports multiple languages from the start of the MVP, initially Ukrainian and English.

**Frontend:**
- `react-i18next`, separate translation files `uk.json` / `en.json` for all UI chrome (labels, statuses, legend, buttons, disclaimer).
- A language switcher in the UI; defaults to the browser language (`navigator.language`), with the user's choice persisted (localStorage or backend user config).

**Backend / data:**
- The `districts` table gets `name_uk` and `name_en` columns instead of a single `name` — a district name has an English counterpart for the UI regardless of the source channel's language.
- The API returns district names in both languages (or via a `?lang=` parameter), and the frontend picks the one it needs.
- **Raw channel message text stays in the source language (Ukrainian)** — it's first-hand data, and translating it on the fly risks accuracy. Instead of automatically translating every message in real time:
  - UI statuses/labels ("confirmed", etc.) always go through the i18n dictionary, never through translation of the raw text;
  - optionally, a "show translation" button for a specific message that makes a one-off call to the Claude API and caches the result in `threat_events.translated_text`, instead of auto-translating the whole stream (keeps cost and latency under control).
- The disclaimer about the source being unofficial must be localized in both languages and shown regardless of the selected UI language.

## 12. Risks
- Free-text parsing accuracy is limited — sightings can be missed or misread; the product must communicate this directly to the user.
- Compliance with Telegram's ToS when reading the public channel; the data must not be used for anything beyond personal/local notification.
- The data source is third-party — an explicit link to the original channel and an "unofficial service" notice must appear on every screen.

from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration. Values come from env vars or a local .env file.

    For the local MVP skeleton, defaults point at a SQLite file so the app
    runs with zero setup. In production, set DATABASE_URL to async Postgres,
    e.g. postgresql+asyncpg://user:pass@host/db
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./kyiv_radar.db"

    @field_validator("database_url")
    @classmethod
    def _async_pg_scheme(cls, v: str) -> str:
        # Railway's Postgres plugin injects DATABASE_URL as plain
        # "postgres://" / "postgresql://" (libpq scheme) — SQLAlchemy's async
        # engine needs the asyncpg driver named explicitly. Rewrite rather
        # than requiring a hand-edited env var on every deploy.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix) and "+asyncpg" not in v:
                return "postgresql+asyncpg://" + v[len(prefix):]
        return v

    # Comma-separated list of allowed CORS origins (the Vite dev server by default).
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Minutes since the last sighting after which a new report starts a NEW
    # track instead of continuing the previous one (spec §5.4).
    track_gap_minutes: int = 15
    # Minutes of silence after which an open track is auto-closed as 'lost' (a
    # target that went quiet without an explicit destroyed/clear). Slightly above
    # the gap so a still-live track isn't closed prematurely.
    track_stale_minutes: int = 20
    # Prefer Telegram reply-threading over time-proximity for track grouping: a
    # message replying to a previous OPEN post joins THAT post's track
    # (transitively). This is the fix for busy-alert "mega-track" zigzags.
    reply_grouping_enabled: bool = True
    # For a non-reply (or broken-reply) sighting we no longer continue "the newest
    # open track" — that re-merged independent targets from non-threaded channels
    # into one zigzag. Instead we only continue a track that this sighting
    # CORROBORATES: an open track seen over the SAME district within this window.
    # Otherwise it starts its own (possibly short) track. This is a same-target
    # MERGE rule between reports, NOT a distance/trajectory threshold.
    # Empirically tuned 2026-07-09 (eval/track_eval.py against 74 hand-labeled
    # real target sessions, backfilled from all 3 channels): swept 10/7/5/4/3/2
    # minutes — 3 minimized false-merges of genuinely different targets that
    # happen to transit the same busy corridor district (Бровари, Троєщина,
    # Славутич/Десна) minutes apart during a multi-wave night, with ZERO loss of
    # legitimate corroboration (session-purity unchanged from the window=10
    # baseline; real cross-channel corroborations in the dataset land within
    # ~1-2 min). Below 3 the metric reverses — starts cutting genuine matches.
    corroboration_window_minutes: int = 3

    # Cross-message target-type inheritance (per channel): the rule parser is
    # per-message and stateless, but spotters routinely state the TYPE in one
    # post ("Балістика!", "3 ракети") and the LOCATION in the next bare-toponym
    # post ("Троя", "Вишневе") — so a district event would land as "unknown"
    # even mid-ballistic-attack. When a district-bearing message has no type of
    # its own, inherit the most recent stated type from the SAME source within
    # this window. Rule-only, in-memory — never triggers an LLM call (a message
    # that already has a district short-circuits the LLM fallback gate anyway).
    type_inherit_window_minutes: int = 5

    # --- Incident grouping (Stage E) ---
    # A new track/impact/city-alert joins the current OPEN incident if the
    # incident saw activity within this window, else it starts a fresh incident.
    # Wider than track windows — one attack can have multi-minute lulls between
    # waves yet is still "the same attack".
    incident_gap_minutes: int = 30
    # An incident with no member activity for this long is auto-ended by the
    # sweeper (slightly above the gap so a still-live attack isn't ended early).
    incident_stale_minutes: int = 40
    # Two impact reports over the SAME district within this window are treated as
    # the SAME strike (two sources, one hit) — the later one corroborates the
    # first marker instead of stacking a second pin on the same point.
    impact_dedup_minutes: int = 20
    # How long a confirmed-strike (impact) marker stays on the LIVE map. Impacts
    # are closed-on-creation but persist as pins; without a cap they'd accumulate
    # across days and clutter the map with strikes from old attacks. History/feed
    # keep them regardless — this only bounds the live map layer.
    impact_map_ttl_hours: int = 6

    # One-off maintenance: when true, rebuild ALL tracks/incidents from stored
    # raw_messages at startup (BEFORE the live listener starts — race-free) so a
    # prod DB picks up parser/gazetteer changes without external DB access. Set
    # it, let the service redeploy once, then unset it (it re-runs every boot
    # while set). Rule-only (no LLM) so it costs nothing.
    reprocess_on_boot: bool = False

    # Emit synthetic tracks (as raw Ukrainian text through the REAL parser) so
    # the frontend has live data before Telegram credentials are configured.
    simulator_enabled: bool = True
    # Replay real captured messages (app/data/real_sample_messages.jsonl — 871
    # messages backfilled 2026-07-05..09, see eval/ground_truth_sessions.json)
    # through the real pipeline instead of the synthetic simulator, preserving
    # their original reply chains so tracks/vectors look like the real thing.
    # Takes priority over simulator_enabled; still skipped if telegram_enabled.
    replay_real_data: bool = False

    # --- Real Telegram feed (Telethon). Off until credentials are set. ---
    telegram_enabled: bool = False
    telegram_api_id: int = 0

    @field_validator("telegram_api_id", mode="before")
    @classmethod
    def _blank_api_id_is_unset(cls, v):
        # A platform env-var UI can leave this set-but-empty (rather than
        # absent) — treat that the same as "not configured" instead of
        # crashing the whole app on an int-parse error before it even starts.
        return 0 if v == "" else v
    telegram_api_hash: str = ""
    telegram_session: str = "kyiv_radar.session"
    # Alternative to telegram_session for platforms with an ephemeral filesystem
    # (Railway): a Telethon StringSession held entirely in an env var, no
    # session file/volume needed. Takes priority over telegram_session when set.
    telegram_session_string: str = ""
    # Comma-separated channel usernames/handles to read (without @).
    telegram_channels: str = ""
    # On startup, ingest this many recent messages per channel (0 = none). Gives
    # the map immediate data and tests the parser on real posts.
    telegram_backfill: int = 15
    # A connected session with no LIVE message for this long is flagged
    # unhealthy (see telegram_listener.py::feed_health) — a dead/zombied
    # Telethon connection now matters more than it used to (Phase 2's
    # absence-of-відбій alert logic depends on the feed actually being
    # alive). No real-traffic data to tune this against yet; picked long
    # enough to tolerate a genuinely quiet night without false-alarming,
    # short enough to catch a dead session the same night rather than days
    # later — adjust with real operational experience.
    feed_silence_warn_minutes: int = 90
    # Analysis mode: stream backfilled events to the UI (feed + map) with a small
    # delay, as if arriving live. Off for normal startup.
    telegram_backfill_broadcast: bool = False

    @property
    def telegram_channel_list(self) -> list[str]:
        return [c.strip().lstrip("@") for c in self.telegram_channels.split(",") if c.strip()]

    # --- Official air-raid alert channel (@KyivCityOfficial). Watched on the
    #     SAME Telethon client as the spotter channels, but routed to
    #     alert_parser.py via Source.role — see telegram_listener.py. Empty =
    #     this phase is fully dormant (the rollback path). ---
    alert_channels: str = ""

    @property
    def alert_channel_list(self) -> list[str]:
        return [c.strip().lstrip("@") for c in self.alert_channels.split(",") if c.strip()]

    # An alert open this long with no відбій is treated as a dead Telethon
    # session that ate the відбій, not a real day-long siren — the sweeper
    # force-closes it (Alert.closed_reason='failsafe') instead of leaving a
    # stuck banner forever.
    alert_failsafe_hours: int = 12

    # Ballistic exception: a ballistic incident often starts BEFORE the
    # official siren (sub-minute flight time leaves no time for the alert to
    # fire first). When a city alert starts, adopt the most recent still-open
    # incident with no alert linked yet, if it began within this many minutes
    # — see app/alerts.py::_adopt_recent_incident.
    alert_adopt_lookback_minutes: int = 10

    # --- LLM fallback parser (Claude Haiku 4.5). Used ONLY for entity extraction
    #     when the rule-based parser is low-confidence; bearing/ETA stay in code. ---
    anthropic_api_key: str = ""
    llm_fallback_enabled: bool = True
    llm_model: str = "claude-haiku-4-5"
    llm_timeout_s: float = 5.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

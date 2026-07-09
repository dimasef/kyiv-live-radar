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
    corroboration_window_minutes: int = 10

    # Emit synthetic tracks (as raw Ukrainian text through the REAL parser) so
    # the frontend has live data before Telegram credentials are configured.
    simulator_enabled: bool = True

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
    # Analysis mode: stream backfilled events to the UI (feed + map) with a small
    # delay, as if arriving live. Off for normal startup.
    telegram_backfill_broadcast: bool = False

    @property
    def telegram_channel_list(self) -> list[str]:
        return [c.strip().lstrip("@") for c in self.telegram_channels.split(",") if c.strip()]

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

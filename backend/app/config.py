from __future__ import annotations

from pydantic import AliasChoices, Field, field_validator
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
    # Ballistic is sub-minute in flight: a localized ballistic DOT hangs on the
    # map far longer than the target is actually airborne, so it clears on a much
    # shorter silence window than the generic one. Applies only to district-scoped
    # ballistic tracks (a scope='city' ballistic alert is the "barrage in
    # progress" banner and keeps the normal window — waves can lull for minutes).
    ballistic_stale_minutes: int = 5
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

    # --- Fusion confidence (app/domain/fusion.py::compute_fusion) — deliberately
    #     simple skeleton weights, not empirically tuned against real multi-source
    #     data yet (see that module's docstring). Base confidence by corroboration
    #     count, then a flat penalty when sources disagree on target-type family. ---
    fusion_conf_one_source: float = 0.5
    fusion_conf_two_sources: float = 0.75
    fusion_conf_three_plus_sources: float = 0.9
    fusion_conflict_penalty: float = 0.2

    # How often the stale-track/incident/alert sweeper runs (app/pipeline/sweeper.py).
    sweeper_interval_s: int = 60

    # WS keepalive: broadcast a 'ping' frame this often so a healthy socket
    # never goes silent for long — the frontend's stale-connection watchdog
    # (60s threshold) then never false-triggers during an otherwise-quiet
    # night. See app/pipeline/keepalive.py.
    ws_keepalive_s: int = 25

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
    # Ingest this many recent messages per channel on EVERY (re)connect (0 =
    # none). On first start it gives the map immediate data; on a reconnect it
    # recovers the gap the listener was blind for — most importantly a missed
    # відбій, which otherwise leaves a stuck alert banner. Sized to comfortably
    # cover the watchdog silence window below; the ingest dedup guard makes
    # re-fetching already-seen messages a cheap no-op.
    telegram_backfill: int = 30
    # A connected session with no LIVE message for this long is flagged
    # unhealthy (see telegram_listener.py::feed_health) — a dead/zombied
    # Telethon connection now matters more than it used to (Phase 2's
    # absence-of-відбій alert logic depends on the feed actually being
    # alive). No real-traffic data to tune this against yet; picked long
    # enough to tolerate a genuinely quiet night without false-alarming,
    # short enough to catch a dead session the same night rather than days
    # later — adjust with real operational experience.
    feed_silence_warn_minutes: int = 90
    # Watchdog: force a reconnect when the LIVE update stream has been silent for
    # this long while Telethon still reports connected — the zombie half-open
    # socket (weak point #7) where run_until_disconnected() never returns on its
    # own, so the reconnect loop never fires (the 2026-07-18 incident: feed dead
    # 01:34->09:51, missed the відбій, banner stuck). Only armed AFTER this
    # connection has delivered at least one live message — a stretch that's been
    # quiet since connect isn't evidence of a zombie, and this also stops a
    # still-dead reconnect from churning. On a truly quiet-then-reconnected feed
    # it's a harmless no-op; on a zombie it caps the blind spot at this window.
    listener_watchdog_silence_minutes: int = 30
    listener_watchdog_interval_s: int = 60
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

    # --- Async LLM triage engine (app/pipeline/triage.py) — the second consumer
    #     of the LLM. Rules answer instantly (sync); a district-less / suppressed
    #     but threat-flavoured message is ALSO handed to an async triage pass that
    #     surfaces directional/forecast/status notices, feeds the axis layer, and
    #     (behind a flag) rescues a wrongly-suppressed live threat. Never holds the
    #     ingest lock during the API call. ---
    # Master switch — off makes the whole context layer dormant (rollback path);
    # rules/inline-fallback behave exactly as before.
    triage_enabled: bool = True
    # Bounded in-process queue; a burst past this drops the oldest-unqueued
    # message (marked triage_state='skipped') rather than growing unboundedly.
    triage_queue_max: int = 200
    # A verdict that lands more than this long after the message is stored for
    # audit only — no live notice/axis/rescue (the situation has moved on).
    triage_max_age_minutes: int = 10

    # --- LLM cost guard (both the inline fallback AND the triage engine). When
    #     the running spend for the current UTC day/month reaches the cap, the LLM
    #     is skipped and the pipeline degrades gracefully to rules-only. 0 =
    #     unlimited. Computed from raw_messages.llm_cost_usd — see
    #     app/pipeline/triage.py::llm_spend_ok. ---
    llm_daily_budget_usd: float = 2.0
    llm_monthly_budget_usd: float = 25.0

    # --- Directional threat axes (app/domain/axes.py). An inbound origin/bearing
    #     callout with no Kyiv raion. ---
    axis_enabled: bool = True
    # Repeat callouts of the same (sector, target-family) within this window fold
    # into ONE axis (the fusion window), bumping its corroboration.
    axis_fusion_window_minutes: int = 5
    # Distinct independent sources needed to promote an axis unverified ->
    # corroborated (a supplementary cue must agree across channels before it reads
    # as more than one volunteer's guess).
    axis_min_sources: int = 2
    # An axis with no new callout for this long is expired off the live layer by
    # the sweeper (slightly above the fusion window).
    axis_ttl_minutes: int = 10

    # --- Rescue path (app/pipeline/triage.py::_route_rescue) — the riskiest
    #     consumer: an LLM verdict re-injecting a suppressed message as a live
    #     track. Ships DISABLED; dark-launch by watching triage_action=
    #     'rescue_candidate' on /raw for a few real nights, then enable. ---
    triage_rescue_enabled: bool = False
    triage_rescue_min_confidence: float = 0.75
    # A rescue older than this is notice-only (a track born past the stale window
    # would be closed by the sweeper on its next tick — pointless). Capped at the
    # stale window in code.
    triage_rescue_max_age_minutes: int = 15

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # --- Web Push + danger-near-home (app/domain/home_danger.py +
    #     app/pipeline/home_push.py). Fully dormant until VAPID keys are set.
    #     Push is SUPPLEMENTARY by policy: wording must never read as the
    #     official air-raid alert — «Допоміжно:» prefix, never «Повітряна
    #     тривога» (see .claude/plans/home-danger.md). ---
    push_enabled: bool = True
    vapid_public_key: str = ""   # base64url uncompressed point (applicationServerKey)
    vapid_private_key: str = ""  # base64url raw EC key or a path to a PEM file
    vapid_subject: str = "mailto:dfimov95@gmail.com"
    # Master switch for the danger evaluation itself (map indication on the
    # client is independent — this only gates the server-side push path).
    home_danger_enabled: bool = True
    # All geometry runs on district CENTROIDS (km-scale coarse), hence the
    # generous slacks below. DANGER = event within home radius + buffer.
    home_danger_buffer_km: float = 2.0
    # WARNING vector test: cross-track distance of home from the track's
    # forward ray must fall within home radius + this slack...
    home_danger_pass_slack_km: float = 3.0
    # ...OR the ray's bearing be within this tolerance of the bearing to home
    # (centroid-derived headings easily lie by 15-20 deg at range)...
    home_danger_angle_tol_deg: float = 20.0
    # ...and the track head must be within this distance of home at all (a
    # correct course 30+ km out isn't yet a warning — it will re-fire closer).
    home_danger_projection_km: float = 20.0
    # Minimum gap before re-pushing the same track to the same subscription
    # after its level oscillated (warning -> none -> warning). Escalation to a
    # HIGHER never-pushed level always pushes regardless.
    home_push_cooldown_minutes: int = 10
    # A home zone on a raion boundary sits in 2-3 raions at once — the
    # ballistic trigger matches ALL of them. A raion covering less than this
    # share of the zone's sampled area ("зовсім трошки") is ignored.
    home_danger_raion_overlap_min: float = 0.1

    @property
    def push_configured(self) -> bool:
        return bool(self.push_enabled and self.vapid_public_key and self.vapid_private_key)

    # --- Observability (app/observability.py). All opt-in: with the token/DSN
    #     empty the SDKs stay fully dormant — no network calls, no behavior
    #     change — so local dev and the test suite run exactly as before. Set on
    #     Railway to light up traces/errors/metrics. ---
    # Pydantic Logfire — primary telemetry (traces + logs + metrics + LLM spans).
    # Empty token => configured in local-only mode (send_to_logfire='if-token-present').
    logfire_token: str = ""
    # Sentry — error aggregation + alerting. Empty => sentry_sdk.init is skipped.
    sentry_dsn: str = ""
    # Environment tag applied to both Logfire and Sentry. Prefer an explicit
    # ENVIRONMENT, else fall back to Railway's auto-injected RAILWAY_ENVIRONMENT
    # (defaults to "production" there) so a deploy is tagged correctly with no
    # manual var; locally, with neither set, it stays "development".
    environment: str = Field(
        "development",
        validation_alias=AliasChoices("ENVIRONMENT", "RAILWAY_ENVIRONMENT"),
    )
    # Emit stdout as one JSON object per line instead of the default text format,
    # so Railway's log viewer can parse/filter structured fields. Off locally.
    log_json: bool = False
    # Trace sampling for Logfire (1.0 = every request; lower on a busy prod).
    trace_sample_rate: float = 1.0


settings = Settings()

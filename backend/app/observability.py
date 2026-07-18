"""Single place that wires up observability — Pydantic Logfire (traces, logs,
metrics, LLM spans) and Sentry (error aggregation/alerts) — mirroring how
`logging_setup.py` centralizes logging so the two entrypoints (main.py's API
process, worker.py's standalone listener) can't drift.

Everything here is OPT-IN: with `LOGFIRE_TOKEN` / `SENTRY_DSN` unset the SDKs
stay dormant (no network egress, no behavior change), so local dev and the test
suite run exactly as before. On Railway, set the env vars to light it up.
"""

from __future__ import annotations

import contextlib
import logging

from .config import settings

log = logging.getLogger("app")

# Flipped True once setup_logfire() has actually run. Until then `ingest_span`
# is a no-op: tests, eval and reprocess scripts that never initialize
# observability build no spans (and trigger no "logfire not configured" warning).
_logfire_active = False


class _NullSpan:
    """Stand-in span when observability is dormant — supports the same
    set_attribute() call sites so the pipeline code stays branch-free."""

    def set_attribute(self, *_args, **_kwargs) -> None:
        pass


@contextlib.contextmanager
def _null_span():
    yield _NullSpan()


def ingest_span(name: str, **attributes):
    """A Logfire span for one pipeline pass — or a no-op when observability
    hasn't been set up (dev/test/reprocess). The returned object always supports
    `.set_attribute(...)`, so callers set the outcome the same way either way.

    With setup done but no `LOGFIRE_TOKEN`, the span is built locally and simply
    not shipped (`send_to_logfire='if-token-present'`) — same dormant-egress
    principle as the rest of this module."""
    if not _logfire_active:
        return _null_span()
    import logfire

    return logfire.span(name, **attributes)


class _DomainMetrics:
    """Domain metrics that auto-instrumentation can't derive — message rate by
    outcome, LLM-fallback hit-rate, and the live gauges (open tracks/axes, listener
    freshness). Instruments are created once `setup_logfire` runs; before that
    every `record_*`/`observe_*` is a no-op, so dev/test/reprocess build nothing
    and need no token.

    Metrics (not spans) on purpose: they survive head-sampling, are cheap to
    aggregate, and are what alert thresholds read (`radar.listener.lag_seconds`
    > N ⇒ "listener is silent")."""

    def __init__(self) -> None:
        self._on = False

    def activate(self) -> None:
        import logfire

        self._messages = logfire.metric_counter(
            "radar.ingest.messages",
            unit="{message}",
            description="Spotter messages ingested, labelled outcome + decision_source.",
        )
        self._llm = logfire.metric_counter(
            "radar.llm.calls",
            unit="{call}",
            description="LLM fallback calls, labelled result=hit|miss (recovered a district or not).",
        )
        self._open_tracks = logfire.metric_gauge(
            "radar.tracks.open", unit="{track}", description="Currently open threat tracks."
        )
        self._open_axes = logfire.metric_gauge(
            "radar.axes.open", unit="{axis}", description="Currently open directional axes."
        )
        self._listener_lag = logfire.metric_gauge(
            "radar.listener.lag_seconds",
            unit="s",
            description="Seconds since the last LIVE Telegram message (listener freshness).",
        )
        self._on = True

    def record_ingest(self, outcome: str, decision_source: str) -> None:
        if not self._on:
            return
        self._messages.add(1, {"outcome": outcome, "decision_source": decision_source})

    def record_llm(self, hit: bool) -> None:
        """One LLM fallback call resolved: `hit` iff it recovered a district."""
        if not self._on:
            return
        self._llm.add(1, {"result": "hit" if hit else "miss"})

    def observe_open(self, tracks: int, axes: int) -> None:
        if not self._on:
            return
        self._open_tracks.set(tracks)
        self._open_axes.set(axes)

    def observe_listener_lag(self, seconds: float) -> None:
        if not self._on:
            return
        self._listener_lag.set(seconds)


# Single shared instance — imported by the pipeline (record_*) and sweeper (observe_*).
metrics = _DomainMetrics()


def setup_sentry() -> None:
    """Init Sentry for error aggregation/alerts. No-op without a DSN.

    Tracing is left to Logfire (traces_sample_rate=0.0) — Sentry here is purely
    the "something threw — capture the stack and alert me" channel, which piggy-
    backs on the existing `log.exception` sites (e.g. main.py's ws_threats)."""
    if not settings.sentry_dsn:
        return
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
            SqlalchemyIntegration(),
        ],
        traces_sample_rate=0.0,
        send_default_pii=False,
    )
    log.info("sentry initialized (env=%s)", settings.environment)


def setup_logfire(app=None) -> None:
    """Configure Logfire and auto-instrument the stack. Safe to call with no
    token — `send_to_logfire='if-token-present'` keeps it local-only then
    (spans are built but not shipped), so nothing leaves the box in dev.

    `app` is the FastAPI instance to instrument; pass None from the standalone
    worker (which has no HTTP app — only the SQLAlchemy/asyncpg/anthropic layers
    matter there)."""
    import logfire

    logfire.configure(
        service_name="kyiv-radar-backend",
        environment=settings.environment,
        # Explicit token (from pydantic .env or a raw env var) wins; with none,
        # 'if-token-present' keeps Logfire local-only — spans built, nothing shipped.
        token=settings.logfire_token or None,
        send_to_logfire="if-token-present",
        console=False,
        # Head sampling — keep every trace at 1.0 (default), dial down on a busy
        # prod via TRACE_SAMPLE_RATE. head=1.0 samples everything, so passing it
        # unconditionally is a no-op at the default and makes the flag real.
        sampling=logfire.SamplingOptions(head=settings.trace_sample_rate),
    )

    if app is not None:
        logfire.instrument_fastapi(app)

    # Import the engine lazily so a missing/broken observability dep can never
    # take down DB setup at import time.
    from .db import engine

    logfire.instrument_sqlalchemy(engine=engine)
    logfire.instrument_asyncpg()
    # HTTPX + Anthropic: the LLM client in parsing/llm.py is created lazily, but
    # instrumentation patches the class, so instrumenting here (before the first
    # call) covers every later request with per-call latency/token spans.
    logfire.instrument_httpx()
    logfire.instrument_anthropic()
    logfire.instrument_system_metrics()

    # Bridge stdlib logging into Logfire so every existing `log.info/warning/
    # exception` across the codebase becomes a span/log without rewriting call
    # sites. Attached to the root logger set up by setup_logging().
    logging.getLogger().addHandler(logfire.LogfireLoggingHandler())
    metrics.activate()
    global _logfire_active
    _logfire_active = True
    log.info("logfire initialized (env=%s)", settings.environment)


def setup_observability(app) -> None:
    """The single hook for the API process — call once after the FastAPI app is
    built (main.py). Order-independent, but keep it after setup_logging() so the
    Logfire handler attaches to the configured root logger."""
    setup_sentry()
    setup_logfire(app)

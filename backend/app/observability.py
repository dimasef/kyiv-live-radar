"""Single place that wires up observability — Pydantic Logfire (traces, logs,
metrics, LLM spans) and Sentry (error aggregation/alerts) — mirroring how
`logging_setup.py` centralizes logging so the two entrypoints (main.py's API
process, worker.py's standalone listener) can't drift.

Everything here is OPT-IN: with `LOGFIRE_TOKEN` / `SENTRY_DSN` unset the SDKs
stay dormant (no network egress, no behavior change), so local dev and the test
suite run exactly as before. On Railway, set the env vars to light it up.
"""

from __future__ import annotations

import logging

from .config import settings

log = logging.getLogger("app")


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
    log.info("logfire initialized (env=%s)", settings.environment)


def setup_observability(app) -> None:
    """The single hook for the API process — call once after the FastAPI app is
    built (main.py). Order-independent, but keep it after setup_logging() so the
    Logfire handler attaches to the configured root logger."""
    setup_sentry()
    setup_logfire(app)

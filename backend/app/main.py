from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .api.auth_routes import router as auth_router
from .api.friends_routes import friends_router
from .api.gamification import gamification_router
from .api.routes import router
from .api.ws import manager
from .config import settings
from .db import SessionLocal
from .feeds.health import feed_health, get_status
from .feeds.simulator import run_simulator
from .logging_setup import setup_logging
from .migrate import upgrade_to_head
from .observability import setup_observability
from .pipeline.ingest import rehydrate_type_context
from .seed import bootstrap_sources_from_env, seed_districts, seed_sources

setup_logging()
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await upgrade_to_head()
    d = await seed_districts()
    s = await seed_sources()
    b = await bootstrap_sources_from_env()
    log.info("db ready; seeded %d districts, %d sources (+%d from env channels)", d, s, b)

    # Restore the per-channel target-type context from stored messages before any
    # feed starts. It lives in memory, so without this a restart mid-wave leaves
    # every bare toponym callout untyped until the channel restates the type —
    # up to a full type_inherit_minutes window (2026-08-21: 22 min of `unknown`).
    async with SessionLocal() as session:
        restored = await rehydrate_type_context(session)
    if restored:
        log.info("restored target-type context for %d channel(s)", restored)

    # One-off maintenance reprocess — runs BEFORE any feed source starts, so it
    # never races a live ingest. Rebuilds all tracks from raw_messages through
    # the current pipeline. Unset REPROCESS_ON_BOOT after one deploy.
    if settings.reprocess_on_boot:
        from .pipeline.reprocess import run_reprocess

        log.warning("REPROCESS_ON_BOOT set — rebuilding all tracks from raw_messages…")
        result = await run_reprocess(no_llm=True)
        log.warning("reprocess complete: %s — now UNSET REPROCESS_ON_BOOT.", result)

    # Feed source: real Telegram listener if configured, else a replay of real
    # captured messages if requested, else the synthetic text simulator.
    tasks: list[asyncio.Task] = []
    if settings.telegram_enabled and settings.telegram_api_id:
        from .feeds.telegram import run_listener

        log.info("starting Telegram listener")
        tasks.append(asyncio.create_task(run_listener()))
    elif settings.replay_real_data:
        from .feeds.replay import run_replay

        log.info("starting replay of real captured messages")
        tasks.append(asyncio.create_task(run_replay()))
    elif settings.simulator_enabled:
        log.info("starting text simulator (no Telegram credentials configured)")
        tasks.append(asyncio.create_task(run_simulator()))

    # Always run the stale-track sweeper.
    from .pipeline.sweeper import run_sweeper

    tasks.append(asyncio.create_task(run_sweeper()))

    # Always run the WS keepalive — clients rely on it to tell a silent-but-
    # healthy night apart from a dead/zombie socket.
    from .pipeline.keepalive import run_keepalive

    tasks.append(asyncio.create_task(run_keepalive()))

    # Air-raid alert zones: poll an external provider for which raions of
    # Київщина/Чернігівщина have a siren. Read-only map context — it touches no
    # table, so a provider outage only greys out its own layer.
    if settings.alert_zones_enabled:
        from .feeds.alert_zones import run_alert_zones

        log.info("starting alert-zone poller (%s)", settings.alert_zones_url)
        tasks.append(asyncio.create_task(run_alert_zones()))

    # Async LLM triage engine: one consumer draining the in-process queue that
    # ingest fills (directional/forecast/status notices, axis fusion, rescue).
    if settings.triage_enabled:
        from .pipeline.triage import run_triage_consumer

        log.info("starting async LLM triage consumer")
        tasks.append(asyncio.create_task(run_triage_consumer()))

    yield

    for task in tasks:
        task.cancel()
    for task in tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Kyiv Aerial Threat Tracker (MVP)", lifespan=lifespan)

app.include_router(router)
app.include_router(auth_router)
app.include_router(friends_router)
app.include_router(gamification_router)

setup_observability(app)


@app.get("/health")
async def health():
    from .models import utcnow

    # server_time is the client's clock reference: the map ages targets against
    # absolute `stale_at` timestamps, and this is what makes that correct on a
    # device whose own clock is wrong. The WS 'ping' frame refreshes it, but the
    # first ping is up to ws_keepalive_s away — so hydrate it here.
    out = {
        "status": "ok",
        "simulator": settings.simulator_enabled,
        "server_time": utcnow().isoformat(),
    }
    if settings.telegram_enabled:
        status = get_status()
        status["feed_ok"] = feed_health(utcnow(), settings.feed_silence_warn_minutes)
        out["telegram"] = status
    return out


@app.websocket("/ws/threats")
async def ws_threats(ws: WebSocket):
    await manager.connect(ws)
    try:
        # We only push; keep the socket open and ignore any inbound frames.
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(ws)
    except Exception:
        log.exception("ws_threats connection dropped unexpectedly")
        await manager.disconnect(ws)


# The ASGI entrypoint uvicorn serves (see railpack.json). CORS MUST be a raw ASGI
# wrapper here, not app.add_middleware — it has to sit outside Logfire's OTel
# instrumentation or cross-origin preflights 500. Full story: docs/cors-preflight.md.
# `app` (the FastAPI instance) stays exported for the ASGITransport tests.
asgi = CORSMiddleware(
    app,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .api.ws import manager
from .config import settings
from .db import init_db
from .seed import seed_districts, seed_sources
from .simulator import run_simulator

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    d = await seed_districts()
    s = await seed_sources()
    log.info("db ready; seeded %d districts, %d sources", d, s)

    # One-off maintenance reprocess — runs BEFORE any feed source starts, so it
    # never races a live ingest. Rebuilds all tracks from raw_messages through
    # the current pipeline. Unset REPROCESS_ON_BOOT after one deploy.
    if settings.reprocess_on_boot:
        from .reprocess import run_reprocess

        log.warning("REPROCESS_ON_BOOT set — rebuilding all tracks from raw_messages…")
        result = await run_reprocess(no_llm=True)
        log.warning("reprocess complete: %s — now UNSET REPROCESS_ON_BOOT.", result)

    # Feed source: real Telegram listener if configured, else a replay of real
    # captured messages if requested, else the synthetic text simulator.
    tasks: list[asyncio.Task] = []
    if settings.telegram_enabled and settings.telegram_api_id and settings.telegram_channel_list:
        from .telegram_listener import run_listener

        log.info("starting Telegram listener")
        tasks.append(asyncio.create_task(run_listener()))
    elif settings.replay_real_data:
        from .replay import run_replay

        log.info("starting replay of real captured messages")
        tasks.append(asyncio.create_task(run_replay()))
    elif settings.simulator_enabled:
        log.info("starting text simulator (no Telegram credentials configured)")
        tasks.append(asyncio.create_task(run_simulator()))

    # Always run the stale-track sweeper.
    from .sweeper import run_sweeper

    tasks.append(asyncio.create_task(run_sweeper()))

    yield

    for task in tasks:
        task.cancel()
    for task in tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Kyiv Aerial Threat Tracker (MVP)", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
async def health():
    out = {"status": "ok", "simulator": settings.simulator_enabled}
    if settings.telegram_enabled:
        from .telegram_listener import get_status

        out["telegram"] = get_status()
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
        await manager.disconnect(ws)

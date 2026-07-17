"""Periodic WS keepalive so a healthy socket never goes silent for long.

Without this, the backend only ever pushes reactively (data on ingest,
'online' on connect/disconnect, 'health' on transition) — a quiet night can
leave a socket silent indefinitely, indistinguishable from a dead/zombie
connection on the client. A steady 'ping' frame gives the frontend watchdog
(see ws.ts) a reliable heartbeat to key off instead.
"""

from __future__ import annotations

import asyncio

from ..api.ws import manager
from ..config import settings
from ..schemas import WSMessage


async def run_keepalive() -> None:
    while True:
        await asyncio.sleep(settings.ws_keepalive_s)
        if manager.online > 0:
            await manager.broadcast(WSMessage(type="ping"))

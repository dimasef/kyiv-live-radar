from __future__ import annotations

import asyncio

from fastapi import WebSocket

from ..schemas import WSMessage


class ConnectionManager:
    """Tracks connected WebSocket clients and broadcasts JSON envelopes.

    Single-instance only. For horizontal scaling this fan-out moves to Redis
    pub/sub (see spec §2); the interface here stays the same.
    """

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, message: WSMessage) -> None:
        payload = message.model_dump(mode="json")
        async with self._lock:
            targets = list(self._clients)
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)


manager = ConnectionManager()

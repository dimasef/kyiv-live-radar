from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket

from ..schemas import WSMessage

log = logging.getLogger("ws")


class ConnectionManager:
    """Tracks connected WebSocket clients and broadcasts JSON envelopes.

    Single-instance only. For horizontal scaling this fan-out moves to Redis
    pub/sub (see spec §2); the interface here stays the same.
    """

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    @property
    def online(self) -> int:
        return len(self._clients)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        # New client gets the live headcount immediately; everyone else sees it grow.
        await self._broadcast_online()

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)
        await self._broadcast_online()

    async def _broadcast_online(self) -> None:
        await self.broadcast(WSMessage(type="online", online=self.online))

    async def broadcast(self, message: WSMessage) -> None:
        payload = message.model_dump(mode="json")
        async with self._lock:
            targets = list(self._clients)
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception as ex:
                log.info("dropping dead WS client: %s", ex)
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)


manager = ConnectionManager()

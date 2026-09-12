from __future__ import annotations

import asyncio
import logging
import time
from collections import deque

from fastapi import WebSocket

from ..config import settings
from ..observability import metrics
from ..schemas import WSMessage

log = logging.getLogger("ws")

# Heartbeat and headcount frames are not part of the replayable stream: they
# carry the current position but never advance it.
_UNSEQUENCED = frozenset({"ping", "online"})


class ConnectionManager:
    """Tracks connected WebSocket clients and broadcasts JSON envelopes.

    Every data frame gets a position (`epoch`, `seq`) and is kept in a bounded
    history, so GET /sync can hand a reconnecting client exactly the frames it
    missed. Single-instance only: for horizontal scaling both the fan-out and
    the history move to Redis pub/sub (see spec §2); the interface stays.
    """

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._online_task: asyncio.Task | None = None
        self.epoch = int(time.time())
        self.seq = 0
        self._history: deque[tuple[int, str]] = deque(maxlen=settings.ws_history_frames)

    @property
    def online(self) -> int:
        return len(self._clients)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        metrics.observe_ws_clients(self.online)
        # The newcomer gets the headcount (and the stream position) at once;
        # everyone else sees the count in the next coalesced 'online' frame.
        await self._send(ws, self._online_frame())
        self._schedule_online()

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)
        metrics.observe_ws_clients(self.online)
        self._schedule_online()

    def _online_frame(self) -> str:
        return self._stamp(WSMessage(type="online", online=self.online))

    def _schedule_online(self) -> None:
        if self._online_task is None or self._online_task.done():
            self._online_task = asyncio.create_task(self._broadcast_online_later())

    async def _broadcast_online_later(self) -> None:
        await asyncio.sleep(settings.ws_online_coalesce_s)
        await self._broadcast_text(self._online_frame())

    def _stamp(self, message: WSMessage) -> str:
        """Assign the frame its stream position and serialize it once."""
        if message.type not in _UNSEQUENCED:
            self.seq += 1
        message.epoch = self.epoch
        message.seq = self.seq
        text = message.model_dump_json()
        if message.type not in _UNSEQUENCED:
            self._history.append((self.seq, text))
        return text

    def frames_after(self, epoch: int, seq: int) -> list[str] | None:
        """The serialized frames a client positioned at (epoch, seq) has not
        seen — empty if none, None if the gap cannot be replayed (another
        process, or a position older than the history keeps)."""
        if epoch != self.epoch or seq > self.seq:
            return None
        if seq == self.seq:
            return []
        if not self._history or self._history[0][0] > seq + 1:
            return None
        return [text for s, text in self._history if s > seq]

    async def broadcast(self, message: WSMessage) -> None:
        await self._broadcast_text(self._stamp(message))

    async def _broadcast_text(self, text: str) -> None:
        async with self._lock:
            targets = list(self._clients)
        if not targets:
            return
        started = time.perf_counter()
        results = await asyncio.gather(*(self._send(ws, text) for ws in targets))
        dead = [ws for ws, ok in zip(targets, results, strict=True) if not ok]
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)
            metrics.observe_ws_clients(self.online)
        metrics.record_broadcast(time.perf_counter() - started)

    async def _send(self, ws: WebSocket, text: str) -> bool:
        try:
            await asyncio.wait_for(ws.send_text(text), timeout=settings.ws_send_timeout_s)
            return True
        except Exception as ex:
            log.info("dropping dead WS client: %s", ex)
            return False


manager = ConnectionManager()

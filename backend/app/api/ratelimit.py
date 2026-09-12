"""In-memory sliding-window rate limits, keyed by client IP or by an explicit key.

Single-process by design (the same assumption realtime/ws.py makes): the map
runs as one uvicorn worker, so a dict is the whole store. Moving to several
workers means moving this to Redis; the `hit()` interface stays.

The client IP is whatever uvicorn puts in `request.client` — behind Railway's
proxy that is only the real address with `--proxy-headers` (railpack.json).
"""

from __future__ import annotations

import time
from collections import deque

from fastapi import HTTPException, Request

from ..config import settings

_MAX_KEYS = 20_000


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}

    def hit(self, key: str, limit: int, window_s: float, now: float | None = None) -> float:
        """Record one hit; return 0 when allowed, else seconds until the window
        frees a slot (the Retry-After value)."""
        if not settings.rate_limit_enabled:
            return 0.0
        now = time.monotonic() if now is None else now
        if key not in self._hits and len(self._hits) >= _MAX_KEYS:
            self._hits.pop(next(iter(self._hits)), None)
        q = self._hits.setdefault(key, deque())
        while q and now - q[0] >= window_s:
            q.popleft()
        if len(q) >= limit:
            return window_s - (now - q[0])
        q.append(now)
        return 0.0

    def forget(self, key: str) -> None:
        self._hits.pop(key, None)

    def reset(self) -> None:
        self._hits.clear()


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def enforce(key: str, limit: int, window_s: float) -> None:
    wait = limiter.hit(key, limit, window_s)
    if wait > 0:
        raise HTTPException(
            status_code=429,
            detail="Забагато запитів, спробуйте трохи пізніше",
            headers={"Retry-After": str(max(1, int(wait) + 1))},
        )


def per_ip(scope: str, limit: int, window_s: float = 60.0):
    """A FastAPI dependency: at most `limit` calls per `window_s` per client IP."""

    async def _dep(request: Request) -> None:
        enforce(f"{scope}:{client_ip(request)}", limit, window_s)

    return _dep

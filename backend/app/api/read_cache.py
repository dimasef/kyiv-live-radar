"""One rendered copy of each hydrate response per process.

Every reader opening the map asks the same ten questions, and the answers
change only when the pipeline writes — a few times a minute at the worst of a
raid, against hundreds of identical reads a second when a crowd (or a deploy)
sends everyone through `hydrate()` at once. So the JSON bytes are rendered once
per *generation* of the database and handed out until something is written.

The generation is bumped by SQLAlchemy session events, not by the write sites:
any ORM flush (except one that only stamps `users.last_seen_at` — presence is
never part of a cached response) and any ORM-enabled bulk INSERT/UPDATE/DELETE.
A short TTL is the safety net for writes that bypass the ORM entirely.

A miss is rendered under a per-key lock, so a thousand simultaneous first
requests cost one render, not a thousand.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable

from fastapi import Response
from sqlalchemy import event
from sqlalchemy.orm import ORMExecuteState, Session

from ..config import settings
from ..models import User
from ..observability import metrics

_MAX_ENTRIES = 64

_generation = 0
_entries: OrderedDict[str, tuple[int, float, bytes]] = OrderedDict()
_locks: dict[str, asyncio.Lock] = {}


def generation() -> int:
    return _generation


def bump() -> None:
    global _generation
    _generation += 1


def clear() -> None:
    """Forget everything, locks included — the test suite builds a fresh DB and
    a fresh event loop per test, and a lock outlives neither."""
    _entries.clear()
    _locks.clear()
    bump()


@event.listens_for(Session, "after_flush")
def _on_flush(session: Session, _ctx) -> None:
    touched = [*session.new, *session.dirty, *session.deleted]
    if touched and all(isinstance(o, User) for o in touched):
        return
    bump()


@event.listens_for(Session, "do_orm_execute")
def _on_orm_execute(state: ORMExecuteState) -> None:
    if state.is_insert or state.is_update or state.is_delete:
        bump()


async def cached_json(
    key: str,
    render: Callable[[], Awaitable[bytes]],
    *,
    ttl_s: float | None = None,
    versioned: bool = True,
) -> Response:
    """Serve `render()`'s bytes from the cache while they are still current.

    `versioned=False` is for reference data that changes only through a
    restart (districts): it ignores the write generation and lives on its TTL.
    """
    body, result = await get_bytes(key, render, ttl_s=ttl_s, versioned=versioned)
    metrics.record_cache_read(result)
    return Response(content=body, media_type="application/json", headers={"X-Cache": result})


async def get_bytes(
    key: str,
    render: Callable[[], Awaitable[bytes]],
    *,
    ttl_s: float | None = None,
    versioned: bool = True,
) -> tuple[bytes, str]:
    """The cached body and how it was obtained (hit|miss|bypass) — for
    responses that splice several cached bodies into one (GET /sync)."""
    if not settings.read_cache_enabled:
        return await render(), "bypass"
    ttl = settings.read_cache_ttl_s if ttl_s is None else ttl_s
    hit = _lookup(key, ttl, versioned)
    if hit is not None:
        return hit, "hit"
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        hit = _lookup(key, ttl, versioned)
        if hit is not None:
            return hit, "hit"
        gen = _generation
        body = await render()
        _entries[key] = (gen, time.monotonic(), body)
        _entries.move_to_end(key)
        while len(_entries) > _MAX_ENTRIES:
            _entries.popitem(last=False)
        return body, "miss"


def _lookup(key: str, ttl: float, versioned: bool) -> bytes | None:
    entry = _entries.get(key)
    if entry is None:
        return None
    gen, at, body = entry
    if time.monotonic() - at > ttl or (versioned and gen != _generation):
        return None
    return body



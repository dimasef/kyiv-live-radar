import asyncio

import pytest

from app.models import utcnow
from app.pipeline import keepalive
from app.realtime.sessions import LiveSession
from app.realtime.ws import manager


def _fake_client() -> dict:
    """The manager keys sockets to what is known about the reader behind them
    (realtime/sessions.py) — a bare set no longer stands in for it."""
    return {object(): LiveSession(device_id=None, connected_at=utcnow(), user_agent=None, ip=None)}


@pytest.mark.asyncio
async def test_keepalive_broadcasts_only_with_clients(monkeypatch):
    monkeypatch.setattr(keepalive.settings, "ws_keepalive_s", 0.01)

    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 3:
            raise asyncio.CancelledError()

    monkeypatch.setattr(keepalive.asyncio, "sleep", fake_sleep)

    broadcasts = []
    orig_broadcast = manager.broadcast

    async def spy_broadcast(message):
        broadcasts.append(message)
        await orig_broadcast(message)

    monkeypatch.setattr(manager, "broadcast", spy_broadcast)
    monkeypatch.setattr(manager, "_clients", _fake_client())

    with pytest.raises(asyncio.CancelledError):
        await keepalive.run_keepalive()

    assert broadcasts
    assert all(m.type == "ping" for m in broadcasts)


@pytest.mark.asyncio
async def test_keepalive_skips_broadcast_with_no_clients(monkeypatch):
    monkeypatch.setattr(keepalive.settings, "ws_keepalive_s", 0.01)

    async def fake_sleep(_seconds):
        raise asyncio.CancelledError()

    monkeypatch.setattr(keepalive.asyncio, "sleep", fake_sleep)

    broadcasts = []

    async def spy_broadcast(message):
        broadcasts.append(message)

    monkeypatch.setattr(manager, "broadcast", spy_broadcast)
    monkeypatch.setattr(manager, "_clients", {})

    with pytest.raises(asyncio.CancelledError):
        await keepalive.run_keepalive()

    assert broadcasts == []

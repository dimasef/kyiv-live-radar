import asyncio

import pytest

from app.api.ws import manager
from app.pipeline import keepalive


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
    monkeypatch.setattr(manager, "_clients", {object()})

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
    monkeypatch.setattr(manager, "_clients", set())

    with pytest.raises(asyncio.CancelledError):
        await keepalive.run_keepalive()

    assert broadcasts == []

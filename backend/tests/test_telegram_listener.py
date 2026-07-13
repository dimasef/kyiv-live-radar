"""Unit tests for the Telegram listener's reconnect loop.

These never touch a real Telethon client — `_run_listener_once` is mocked so
we can drive `run_listener()`'s retry/backoff behavior deterministically.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.feeds import telegram as tl


@pytest.fixture(autouse=True)
def _reset_state():
    tl._state["connected"] = False
    tl._state["last_message_at"] = None
    tl._state["last_error"] = None
    yield
    tl._state["connected"] = False
    tl._state["last_message_at"] = None
    tl._state["last_error"] = None


async def test_run_listener_noop_when_not_configured():
    old_channels, old_api_id = settings.telegram_channels, settings.telegram_api_id
    settings.telegram_channels = ""
    settings.telegram_api_id = 0
    try:
        with patch.object(tl, "_run_listener_once", new=AsyncMock()) as run_once:
            await tl.run_listener()
        run_once.assert_not_called()
    finally:
        settings.telegram_channels, settings.telegram_api_id = old_channels, old_api_id


async def test_run_listener_reconnects_with_backoff_after_crashes():
    old_channels, old_api_id = settings.telegram_channels, settings.telegram_api_id
    settings.telegram_channels = "somechannel"
    settings.telegram_api_id = 12345
    try:
        calls = []

        async def fake_run_once(backfill, run_state):
            calls.append(backfill)
            if len(calls) >= 3:
                raise asyncio.CancelledError()
            raise RuntimeError(f"boom {len(calls)}")

        sleeps = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        with patch.object(tl, "_run_listener_once", new=fake_run_once), \
             patch("app.feeds.telegram.asyncio.sleep", new=fake_sleep):
            with pytest.raises(asyncio.CancelledError):
                await tl.run_listener()

        # backfill only requested on the very first connect attempt
        assert calls == [True, False, False]
        # backoff doubles each consecutive failure (no successful connect yet)
        assert sleeps == [5, 10]
        assert tl._state["last_error"] == "boom 2"
        assert tl._state["connected"] is False
    finally:
        settings.telegram_channels, settings.telegram_api_id = old_channels, old_api_id


async def test_run_listener_resets_backoff_after_a_real_connection():
    old_channels, old_api_id = settings.telegram_channels, settings.telegram_api_id
    settings.telegram_channels = "somechannel"
    settings.telegram_api_id = 12345
    try:
        calls = []

        async def fake_run_once(backfill, run_state):
            calls.append(backfill)
            if len(calls) == 1:
                raise RuntimeError("first attempt fails before connecting")
            if len(calls) == 2:
                run_state["reached_connected"] = True
                raise RuntimeError("connected, then dropped")
            raise asyncio.CancelledError()

        sleeps = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        with patch.object(tl, "_run_listener_once", new=fake_run_once), \
             patch("app.feeds.telegram.asyncio.sleep", new=fake_sleep):
            with pytest.raises(asyncio.CancelledError):
                await tl.run_listener()

        # first failure backs off from the initial 5s; the second attempt DID
        # reach "connected" before dying, so the backoff after it resets to
        # the initial value instead of continuing to grow.
        assert sleeps == [5, 5]
    finally:
        settings.telegram_channels, settings.telegram_api_id = old_channels, old_api_id

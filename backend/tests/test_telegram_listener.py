"""Unit tests for the Telegram listener's reconnect loop and health status.

These never touch a real Telethon client — `_run_listener_once` is mocked so
we can drive `run_listener()`'s retry/backoff behavior deterministically.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app import telegram_listener as tl
from app.config import settings

NOW = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _reset_state():
    tl._state["connected"] = False
    tl._state["last_message_at"] = None
    tl._state["last_error"] = None
    yield
    tl._state["connected"] = False
    tl._state["last_message_at"] = None
    tl._state["last_error"] = None


def test_get_status_reflects_state():
    tl._state["connected"] = True
    tl._state["last_error"] = "boom"
    status = tl.get_status()
    assert status == {
        "connected": True,
        "last_message_at": None,
        "last_error": "boom",
    }
    # get_status() must return a copy, not the live dict, so callers can't
    # mutate listener-internal state through the health endpoint.
    status["connected"] = False
    assert tl._state["connected"] is True


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
             patch("app.telegram_listener.asyncio.sleep", new=fake_sleep):
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
             patch("app.telegram_listener.asyncio.sleep", new=fake_sleep):
            with pytest.raises(asyncio.CancelledError):
                await tl.run_listener()

        # first failure backs off from the initial 5s; the second attempt DID
        # reach "connected" before dying, so the backoff after it resets to
        # the initial value instead of continuing to grow.
        assert sleeps == [5, 5]
    finally:
        settings.telegram_channels, settings.telegram_api_id = old_channels, old_api_id


# --- feed_health() ---

def test_feed_health_none_when_telegram_disabled():
    old = settings.telegram_enabled
    settings.telegram_enabled = False
    try:
        assert tl.feed_health(NOW, 90) is None
    finally:
        settings.telegram_enabled = old


def test_feed_health_false_when_disconnected():
    old = settings.telegram_enabled
    settings.telegram_enabled = True
    tl._state["connected"] = False
    try:
        assert tl.feed_health(NOW, 90) is False
    finally:
        settings.telegram_enabled = old


def test_feed_health_true_when_connected_with_no_live_message_yet():
    # Freshly connected, backfill ran but no LIVE message arrived yet — not
    # evidence of a problem, so this must read healthy, not stale.
    old = settings.telegram_enabled
    settings.telegram_enabled = True
    tl._state["connected"] = True
    tl._state["last_message_at"] = None
    try:
        assert tl.feed_health(NOW, 90) is True
    finally:
        settings.telegram_enabled = old


def test_feed_health_true_within_the_warn_window():
    old = settings.telegram_enabled
    settings.telegram_enabled = True
    tl._state["connected"] = True
    tl._state["last_message_at"] = NOW - timedelta(minutes=30)
    try:
        assert tl.feed_health(NOW, 90) is True
    finally:
        settings.telegram_enabled = old


def test_feed_health_false_past_the_warn_window():
    old = settings.telegram_enabled
    settings.telegram_enabled = True
    tl._state["connected"] = True
    tl._state["last_message_at"] = NOW - timedelta(minutes=120)
    try:
        assert tl.feed_health(NOW, 90) is False
    finally:
        settings.telegram_enabled = old

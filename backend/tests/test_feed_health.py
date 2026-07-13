"""Unit tests for app/feeds/health.py — listener health status used by
GET /health and the sweeper's periodic push on change.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.feeds import health

NOW = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _reset_state():
    health._state["connected"] = False
    health._state["last_message_at"] = None
    health._state["last_error"] = None
    yield
    health._state["connected"] = False
    health._state["last_message_at"] = None
    health._state["last_error"] = None


def test_get_status_reflects_state():
    health._state["connected"] = True
    health._state["last_error"] = "boom"
    status = health.get_status()
    assert status == {
        "connected": True,
        "last_message_at": None,
        "last_error": "boom",
    }
    # get_status() must return a copy, not the live dict, so callers can't
    # mutate listener-internal state through the health endpoint.
    status["connected"] = False
    assert health._state["connected"] is True


def test_feed_health_none_when_telegram_disabled():
    old = settings.telegram_enabled
    settings.telegram_enabled = False
    try:
        assert health.feed_health(NOW, 90) is None
    finally:
        settings.telegram_enabled = old


def test_feed_health_false_when_disconnected():
    old = settings.telegram_enabled
    settings.telegram_enabled = True
    health._state["connected"] = False
    try:
        assert health.feed_health(NOW, 90) is False
    finally:
        settings.telegram_enabled = old


def test_feed_health_true_when_connected_with_no_live_message_yet():
    # Freshly connected, backfill ran but no LIVE message arrived yet — not
    # evidence of a problem, so this must read healthy, not stale.
    old = settings.telegram_enabled
    settings.telegram_enabled = True
    health._state["connected"] = True
    health._state["last_message_at"] = None
    try:
        assert health.feed_health(NOW, 90) is True
    finally:
        settings.telegram_enabled = old


def test_feed_health_true_within_the_warn_window():
    old = settings.telegram_enabled
    settings.telegram_enabled = True
    health._state["connected"] = True
    health._state["last_message_at"] = NOW - timedelta(minutes=30)
    try:
        assert health.feed_health(NOW, 90) is True
    finally:
        settings.telegram_enabled = old


def test_feed_health_false_past_the_warn_window():
    old = settings.telegram_enabled
    settings.telegram_enabled = True
    health._state["connected"] = True
    health._state["last_message_at"] = NOW - timedelta(minutes=120)
    try:
        assert health.feed_health(NOW, 90) is False
    finally:
        settings.telegram_enabled = old

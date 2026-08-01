"""Contact presence: the pure derivation (domain/presence.py) and the privacy
boundary it enforces — the online dot is public to friends, the timestamp is not.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain.presence import is_online, needs_stamp, presence_for

WINDOW = timedelta(seconds=90)
THROTTLE = timedelta(seconds=60)
NOW = datetime(2026, 8, 1, 22, 0, 0, tzinfo=UTC)


def ago(seconds: int) -> datetime:
    return NOW - timedelta(seconds=seconds)


def test_online_only_inside_the_window():
    assert is_online(ago(10), NOW, WINDOW) is True
    assert is_online(ago(90), NOW, WINDOW) is True  # boundary is inclusive
    assert is_online(ago(91), NOW, WINDOW) is False


def test_never_seen_is_offline_not_an_error():
    assert is_online(None, NOW, WINDOW) is False


def test_online_tolerates_a_naive_stored_timestamp():
    """SQLite drops tzinfo on round-trip, so the stored value comes back naive
    while utcnow() is aware — comparing them raw would raise."""
    assert is_online(ago(10).replace(tzinfo=None), NOW, WINDOW) is True


def test_stamp_is_throttled():
    assert needs_stamp(None, NOW, THROTTLE) is True
    assert needs_stamp(ago(59), NOW, THROTTLE) is False
    assert needs_stamp(ago(60), NOW, THROTTLE) is True


def test_a_future_timestamp_delays_stamping_but_not_forever():
    """Clock skew leaves a user looking 'recently stamped' until real time
    passes the bad value — a bounded wrong, not a permanent one."""
    assert needs_stamp(NOW + timedelta(hours=1), NOW, THROTTLE) is False
    # ...but it resolves on its own once real time passes it.
    assert needs_stamp(NOW + timedelta(hours=1), NOW + timedelta(hours=2), THROTTLE) is True


def test_timestamp_is_withheld_without_opt_in():
    online, seen = presence_for(
        last_seen_at=ago(600), share_presence=False, now=NOW, window=WINDOW
    )
    assert (online, seen) == (False, None)


def test_timestamp_is_disclosed_when_shared_and_offline():
    online, seen = presence_for(
        last_seen_at=ago(600), share_presence=True, now=NOW, window=WINDOW
    )
    assert online is False
    assert seen == ago(600)


def test_online_is_visible_even_without_the_opt_in():
    """The chosen privacy split: presence 'now' is not gated, history is."""
    online, seen = presence_for(
        last_seen_at=ago(5), share_presence=False, now=NOW, window=WINDOW
    )
    assert (online, seen) == (True, None)


def test_no_timestamp_while_online_even_when_shared():
    """'Online' already answers the question; emitting a live timestamp would
    hand a watcher a second-by-second activity log."""
    online, seen = presence_for(
        last_seen_at=ago(5), share_presence=True, now=NOW, window=WINDOW
    )
    assert (online, seen) == (True, None)

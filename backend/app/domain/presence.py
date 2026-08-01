"""Contact presence: is a user in the app right now, and when were they last.

Pure and I/O-free. Presence is derived from `User.last_seen_at`, which
auth/deps.py stamps on authenticated requests — there is no separate heartbeat
endpoint and no socket registry, so "online" really means "made an authenticated
request recently". The frontend polls the friend graph every 30s while
foregrounded, which is what keeps an open tab inside the window.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..timeutil import naive


def is_online(last_seen_at: datetime | None, now: datetime, window: timedelta) -> bool:
    if last_seen_at is None:
        return False
    return naive(now) - naive(last_seen_at) <= window


def needs_stamp(last_seen_at: datetime | None, now: datetime, throttle: timedelta) -> bool:
    """Whether `last_seen_at` is stale enough to be worth a write. Without this
    every authenticated request would UPDATE the users row — the friend poll
    alone is one per 30s per open tab."""
    if last_seen_at is None:
        return True
    # A future timestamp (clock skew) reads as "just stamped" and suppresses
    # writes until real time passes it — bounded by the skew, so not worth
    # clamping.
    return naive(now) - naive(last_seen_at) >= throttle


def presence_for(
    *,
    last_seen_at: datetime | None,
    share_presence: bool,
    now: datetime,
    window: timedelta,
) -> tuple[bool, datetime | None]:
    """(online, last_seen_to_disclose) for showing one user to an accepted friend.

    The timestamp is withheld unless they opted in, and is omitted while they are
    online anyway — "online" already answers the question, and a live timestamp
    would leak activity history to anyone watching the list.
    """
    online = is_online(last_seen_at, now, window)
    if online or not share_presence:
        return online, None
    return False, last_seen_at

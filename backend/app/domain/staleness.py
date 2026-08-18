"""When a track counts as stale — the single source of that rule.

The sweeper closes a silent track (`close_stale_tracks`), and the API publishes
the same instant as `stale_at` so the map can fade a target out exactly as its
auto-close approaches. Both must agree, so neither computes the window itself.

Pure and I/O-free: takes a loaded Threat (or plain row-like object with
`target_type`, `scope`, `created_at`, `events`) plus the window settings.
"""

from __future__ import annotations

from datetime import datetime, timedelta


def stale_window_minutes(
    target_type: str,
    scope: str,
    *,
    minutes: int,
    ballistic_minutes: int | None = None,
) -> int:
    """Minutes of silence this track is allowed before it's auto-closed.

    `ballistic_minutes` (when set) is a SHORTER window for a district-scoped
    ballistic dot: sub-minute flight means such a track hangs on the map long
    after impact. A scope='city' ballistic alert (the barrage banner) keeps the
    normal window — its waves can lull for minutes.
    """
    if ballistic_minutes is not None and target_type == "ballistic" and scope != "city":
        return ballistic_minutes
    return minutes


def last_event_at(threat) -> datetime:
    """When this track was last seen.

    `Threat.events` is ordered by `event_time`, so the tail is the latest
    sighting; a track with no events yet falls back to its creation time.
    Requires `events` to be loaded (the sweeper and `threat_out` both eager-load
    them) — never call it on a shallow row.
    """
    return threat.events[-1].event_time if threat.events else threat.created_at


def stale_at(
    threat,
    *,
    minutes: int,
    ballistic_minutes: int | None = None,
) -> datetime:
    """The instant the sweeper will consider this track stale.

    Note it can be in the past: the sweep runs on a fixed interval, so a track
    stays open for up to one tick after crossing its window.
    """
    window = stale_window_minutes(
        threat.target_type, threat.scope, minutes=minutes, ballistic_minutes=ballistic_minutes
    )
    return last_event_at(threat) + timedelta(minutes=window)

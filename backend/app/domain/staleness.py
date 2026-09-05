"""When a track counts as stale — the single source of that rule.

The sweeper closes a silent track (`close_stale_tracks`), and the API publishes
the same instant as `stale_at` so the map can fade a target out exactly as its
auto-close approaches. Both must agree, so neither computes the window itself.

The window is picked on TWO axes, both measured against real feed data:

* **target type** — how fast the thing moves, i.e. how long the dot we drew
  stays true. On real multi-event tracks the same target is re-reported over a
  DIFFERENT district within 3.1-3.6 min at p90, for every type — a position fix
  simply does not survive longer than that.
* **whether the track is actually being followed** — a track whose events form a
  resolved Telegram reply chain is one a channel is walking along, and its
  callouts legitimately pause for 8-25 min; a track with no reply chain is a
  one-shot sighting that nothing will ever join (a reply can't arrive, and
  corroboration only merges the SAME district within
  `corroboration_window_minutes`), so holding it open buys no grouping at all
  and only leaves a ghost on the map.

That second axis is the one that matters most right now: on the night of
2026-08-20, 144 of 153 tracks had no reply chain at all (the one channel that
threads posted 2 messages), and a single reactive drone crossing the city was
drawn as 18 simultaneous live targets, each holding the full 20-minute window.

Pure and I/O-free: takes a loaded Threat (or plain row-like object with
`target_type`, `scope`, `created_at`, `events`) plus the window settings.
"""

from __future__ import annotations

from datetime import datetime, timedelta


def is_reply_tracked(threat) -> bool:
    """Whether this track was built by a RESOLVED reply chain.

    Mirrors how `find_track_by_reply` grouped the events in the first place:
    Telegram reply ids are channel-scoped, so a link counts only when some event
    replies to another event of the SAME track on the SAME source. A dangling
    `reply_to_message_id` (the parent was never parsed, so the reply started this
    track instead of joining one) is NOT evidence anyone is following the target
    — which is exactly the case that would otherwise buy a broken chain the long
    window it hasn't earned.

    Requires `events` to be loaded, like everything else here.
    """
    seen = {
        (e.source_id, e.source_message_id)
        for e in threat.events
        if e.source_message_id is not None
    }
    return any(
        e.reply_to_message_id is not None and (e.source_id, e.reply_to_message_id) in seen
        for e in threat.events
    )


def reply_tracked_sources(threat) -> set[int]:
    """Sources with a resolved reply on this track — the ones actually walking
    the target, per source rather than per track."""
    seen = {
        (e.source_id, e.source_message_id)
        for e in threat.events
        if e.source_message_id is not None
    }
    return {
        e.source_id for e in threat.events
        if e.reply_to_message_id is not None and (e.source_id, e.reply_to_message_id) in seen
    }


def stale_window_minutes(
    target_type: str,
    scope: str,
    *,
    tracked: bool,
    orphan_windows: dict[str, int],
    tracked_windows: dict[str, int],
    default_minutes: int,
) -> int:
    """Minutes of silence this track is allowed before it's auto-closed.

    A scope='city' track (the barrage banner) keeps `default_minutes`, the
    longest window there is, whatever its type: it has no dot on the map that
    could be wrong about where the target is — it's a "this is happening to the
    city" state — and a multi-wave night lulls for minutes between salvos.

    An unknown `target_type` falls back to `default_minutes` too, rather than
    guessing — a new type added to the model without a window here should behave
    like the old single-window world, not vanish in two minutes.
    """
    if scope == "city":
        return default_minutes
    windows = tracked_windows if tracked else orphan_windows
    return windows.get(target_type, default_minutes)


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
    orphan_windows: dict[str, int],
    tracked_windows: dict[str, int],
    default_minutes: int,
    rule: str = "legacy",
) -> datetime:
    """The instant the sweeper will consider this track stale.

    'legacy': the track's last event plus one window. 'per_source': each source
    gets its own window from its own last event — the reply narrator's long one,
    an echo channel's short one — and the track lives while any source is still
    inside its window. An echo posting every 1.5 min then holds the track open
    5 min past its last post, not 15 past the narrator's.

    Note it can be in the past: the sweep runs on a fixed interval, so a track
    stays open for up to one tick after crossing its window.
    """
    def window(tracked: bool) -> timedelta:
        return timedelta(minutes=stale_window_minutes(
            threat.target_type, threat.scope, tracked=tracked,
            orphan_windows=orphan_windows, tracked_windows=tracked_windows,
            default_minutes=default_minutes,
        ))

    if rule != "per_source" or not threat.events:
        return last_event_at(threat) + window(is_reply_tracked(threat))
    narrators = reply_tracked_sources(threat)
    last_by_source: dict = {}
    for e in threat.events:
        t = _naive(e.event_time)
        if e.source_id not in last_by_source or t > last_by_source[e.source_id]:
            last_by_source[e.source_id] = t
    return max(
        last + window(sid in narrators) for sid, last in last_by_source.items()
    )


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt

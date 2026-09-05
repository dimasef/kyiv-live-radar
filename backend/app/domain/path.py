"""Which sightings draw a track's path.

Echo channels repost a narrator's callouts seconds later with their own place
names; drawn together the sources zigzag (measured on a live week: +29% path
length, +44% turns >120° on narrated tracks). One source leads the polyline:
the reply-chain narrator, else the source with the most events, latched so it
does not flip on every message. Everything else is echo — kept, counted for
corroboration, not drawn as the path.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from ..config import settings
from ..timeutil import naive


def narrator_source_id(events: Sequence) -> int | None:
    posted = {
        (e.source_id, e.source_message_id) for e in events if e.source_message_id is not None
    }
    replies = [
        e for e in events
        if e.reply_to_message_id is not None and (e.source_id, e.reply_to_message_id) in posted
    ]
    if not replies:
        return None
    return max(replies, key=lambda e: naive(e.event_time)).source_id


def dominant_source_id(events: Sequence, current: int | None) -> int | None:
    counts: dict[int, int] = {}
    first_seen: dict[int, datetime] = {}
    for e in events:
        if e.source_id is None:
            continue
        counts[e.source_id] = counts.get(e.source_id, 0) + 1
        t = naive(e.event_time)
        if e.source_id not in first_seen or t < first_seen[e.source_id]:
            first_seen[e.source_id] = t
    if not counts:
        return None
    best = min(counts, key=lambda sid: (-counts[sid], first_seen[sid]))
    if current is None or current not in counts:
        return best
    return best if counts[best] >= counts[current] + 2 else current


def path_source_id(events: Sequence, current: int | None) -> int | None:
    narrator = narrator_source_id(events)
    if narrator is not None:
        return narrator
    return dominant_source_id(events, current)


def path_events(events: Sequence, path_source_id: int | None) -> list:
    if path_source_id is None or not settings.path_rule_enabled:
        return list(events)
    return [e for e in events if e.source_id == path_source_id or e.attached_by == "manual"]


def path_head(events: Sequence, path_source_id: int | None):
    located = [e for e in path_events(events, path_source_id) if e.district is not None]
    return max(located, key=lambda e: naive(e.event_time)) if located else None


def refresh_path(threat) -> None:
    """Recompute `path_source_id` and `movement_stated` from the loaded events.
    Called from `set_fusion`, so every place that adds, moves or deletes a
    sighting keeps both current."""
    if settings.path_rule_enabled:
        threat.path_source_id = path_source_id(threat.events, threat.path_source_id)
    own = path_events(threat.events, threat.path_source_id)
    threat.movement_stated = any(e.frame == "path" for e in own)

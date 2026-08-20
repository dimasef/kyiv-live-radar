"""Central track lifecycle: the single place that closes or promotes a Threat.

These mutations used to be inlined across ingest.py/tracking.py, and
`status='lost'` was overloaded to mean three different things (відбій /
дорозвідка stand-down / silence timeout) with no way to tell them apart after
the fact. `closed_reason` makes the actual reason explicit; `status` is kept
in sync for backwards-compat, since the serializer/frontend still read it.

No state-machine library — a plain transition table is enough for a
single-process MVP with one lock serializing all mutations.
"""

from __future__ import annotations

import logging
from datetime import datetime

from ..models import Threat

log = logging.getLogger("tracking")

# Legal status transitions — documents intent; not enforced at runtime (every
# caller already only closes/promotes a track it just confirmed is open).
TRACK_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "unconfirmed": ("tracking", "destroyed", "lost"),
    "tracking": ("destroyed", "lost"),
    "destroyed": (),
    "lost": (),
    "impact": (),
}

# The legacy `status` value implied by each closed_reason, so existing
# consumers of `status` (frontend, older API clients) keep working unchanged.
CLOSED_REASON_TO_STATUS: dict[str, str] = {
    "destroyed": "destroyed",
    "all_clear": "lost",
    "stand_down": "lost",
    "stale": "lost",
    # Admin manual cancel — its own status so a false positive never reads as a
    # real 'lost'/'destroyed' target and is easy to exclude from stats/journal.
    "dismissed": "dismissed",
}


def close_track(threat: Threat, when: datetime, reason: str) -> Threat:
    """Close an open track with an explicit domain reason.

    Sets `closed_at`/`closed_reason` and derives the legacy `status`. Callers
    are expected to only call this on a track that is still open."""
    if reason not in CLOSED_REASON_TO_STATUS:
        raise ValueError(f"unknown closed_reason: {reason!r}")
    threat.status = CLOSED_REASON_TO_STATUS[reason]
    threat.closed_at = when
    threat.closed_reason = reason
    log.info("track %s closed (reason=%s)", threat.id, reason)
    return threat


def relabel_close(threat: Threat, reason: str) -> Threat:
    """Correct WHY an already-closed track closed, without moving `closed_at`.

    A «збито» can arrive after the sweeper has already retired the track as
    silent — more often since the stale windows became per-type (measured: ~16%
    of closing messages). The target really was destroyed, so recording it as
    'stale' loses a confirmed interception from the journal.

    `closed_at` deliberately stays put: it's when the track left the map, which
    the relabel doesn't change, and moving it would stretch the track's duration
    in the journal by the silence that preceded the news. The track is NOT
    reopened — it's gone from the map for the right reason already."""
    if reason not in CLOSED_REASON_TO_STATUS:
        raise ValueError(f"unknown closed_reason: {reason!r}")
    if threat.closed_at is None:
        raise ValueError("relabel_close is for an already-closed track; use close_track")
    was = threat.closed_reason
    threat.closed_reason = reason
    threat.status = CLOSED_REASON_TO_STATUS[reason]
    log.info("track %s close relabelled %s -> %s", threat.id, was, reason)
    return threat


def promote_track(threat: Threat) -> Threat:
    """Mark a track as actively confirmed-tracking (vs. merely 'unconfirmed'),
    once a source reports it without hedging language."""
    threat.status = "tracking"
    log.info("track %s promoted to tracking", threat.id)
    return threat


def reopen_track(threat: Threat) -> Threat:
    """Reverse a stand-down close: a pulse / city-wide callout arriving within
    the grace window means the stand-down was a between-waves lull, not the
    end — the SAME alert continues instead of spawning a duplicate card."""
    threat.status = "tracking"
    threat.closed_at = None
    threat.closed_reason = None
    log.info("track %s reopened after stand-down", threat.id)
    return threat

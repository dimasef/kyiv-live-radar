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

from datetime import datetime

from .models import Threat

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
    return threat


def promote_track(threat: Threat) -> Threat:
    """Mark a track as actively confirmed-tracking (vs. merely 'unconfirmed'),
    once a source reports it without hedging language."""
    threat.status = "tracking"
    return threat

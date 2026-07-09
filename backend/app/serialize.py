"""Shared ORM -> API/WS serialization (used by REST routes and WS broadcaster)."""

from __future__ import annotations

from .models import Threat, ThreatEvent
from .schemas import FeedEntryOut, ThreatEventOut, ThreatOut


def event_out(ev: ThreatEvent) -> ThreatEventOut:
    out = ThreatEventOut.model_validate(ev)
    if ev.district is not None:
        out.lat = ev.district.lat
        out.lon = ev.district.lon
    if ev.source is not None:
        out.source_name = ev.source.name
    return out


def threat_out(th: Threat) -> ThreatOut:
    out = ThreatOut.model_validate(th)
    out.events = [event_out(ev) for ev in th.events]
    return out


def threat_out_shallow(th: Threat) -> ThreatOut:
    """Threat fields only, events=[] — for contexts where each event already
    carries its own row (the feed) and loading every track's full event list
    would be wasteful (and would require eager-loading th.events, which isn't
    for a plain event query)."""
    return ThreatOut(
        id=th.id,
        created_at=th.created_at,
        target_type=th.target_type,
        status=th.status,
        target_count=th.target_count,
        closed_at=th.closed_at,
        corroboration_count=th.corroboration_count,
        has_conflict=th.has_conflict,
        confidence=th.confidence,
        events=[],
    )


def feed_entry_out(ev: ThreatEvent) -> FeedEntryOut:
    return FeedEntryOut(event=event_out(ev), threat=threat_out_shallow(ev.threat))

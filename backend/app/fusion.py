from __future__ import annotations

from collections.abc import Iterable

from .models import ThreatEvent


class FusionResult:
    __slots__ = ("corroboration_count", "has_conflict", "confidence")

    def __init__(self, corroboration_count: int, has_conflict: bool, confidence: float):
        self.corroboration_count = corroboration_count
        self.has_conflict = has_conflict
        self.confidence = confidence


def _origin_key(ev: ThreatEvent):
    """Independent-origin key for an event.

    Identity is the ORIGINAL message: a repost carries it in `forwarded_from_id`,
    an original post is identified by its own `source_message_id`. Both collapse
    to the same key, so N channels echoing one post count as ONE independent
    confirmation — not N. Falls back to the source channel when no message id is
    available.

    Limitation (MVP): keyed on message id alone, not (channel, id). Telegram ids
    are per-channel, so two unrelated originals sharing a numeric id would merge.
    Storing the original channel on reposts (Telethon `fwd_from`) removes this.
    """
    if ev.forwarded_from_id is not None:
        return ("orig", ev.forwarded_from_id)
    if ev.source_message_id is not None:
        return ("orig", ev.source_message_id)
    return ("src", ev.source_id)


def compute_fusion(events: Iterable[ThreatEvent]) -> FusionResult:
    """Derive corroboration, conflict, and fused confidence for a track.

    NOTE: this is the deliberately-simple skeleton version. The real fusion
    (time-windowed correlation, trust-weighting, spatial consistency, entity
    resolution across phrasings) lands once we have live channels and an eval
    set. The data model already carries everything that richer logic needs.
    """
    events = list(events)
    origins = {_origin_key(ev) for ev in events}
    corroboration = max(1, len(origins))

    claimed_types = {ev.event_target_type for ev in events if ev.event_target_type}
    has_conflict = len(claimed_types) > 1

    if corroboration <= 1:
        base = 0.5
    elif corroboration == 2:
        base = 0.75
    else:
        base = 0.9
    if has_conflict:
        base -= 0.2

    return FusionResult(corroboration, has_conflict, round(max(0.1, base), 2))

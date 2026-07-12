from __future__ import annotations

from collections.abc import Iterable

from .models import ThreatEvent


class FusionResult:
    __slots__ = ("corroboration_count", "has_conflict", "confidence")

    def __init__(self, corroboration_count: int, has_conflict: bool, confidence: float):
        self.corroboration_count = corroboration_count
        self.has_conflict = has_conflict
        self.confidence = confidence


def _origin_keys(events: list[ThreatEvent]) -> set:
    """Independent-origin key per event, for the whole track at once.

    Identity is the reporting SOURCE CHANNEL — several messages from the SAME
    channel narrating one track over time (a sighting, then an update, then
    "destroyed") must collapse to ONE origin, not one per message. A repost
    carries the ORIGINAL post's id in `forwarded_from_id`; when that original
    is also one of this track's own (non-forwarded) events, the repost is
    attributed to THAT original's channel — so it collapses with it instead
    of counting as a second corroborating source. If the original isn't
    present in this track (came from an untracked channel), the repost falls
    back to its own `("orig", forwarded_from_id)` key.

    (Naively keying non-reposts on bare `source_message_id` was tried and
    reverted — every message has a unique id even within one channel, so that
    made EVERY additional message from the SAME channel look like a new
    independent source, silently inflating corroboration_count/confidence on
    any track with 2+ updates from one channel — found via a real track that
    showed "2 джерел" despite both events being from the same channel. But
    bare source_id alone breaks repost collapsing, since a repost's
    `forwarded_from_id` and the original's own `source_message_id` share the
    same numeric id — the two-pass approach here keeps both correct.)

    The fallback key includes `forwarded_from_channel_id` (the origin
    channel's Telegram peer id, captured from `fwd_from` at ingest — see
    telegram_listener.py) alongside the bare message id, so two unrelated
    originals from different channels that happen to share a numeric id no
    longer incorrectly merge into one origin.
    """
    original_channel_by_msgid = {
        ev.source_message_id: ev.source_id
        for ev in events
        if ev.forwarded_from_id is None and ev.source_message_id is not None
    }
    keys = set()
    for ev in events:
        if ev.forwarded_from_id is not None:
            src = original_channel_by_msgid.get(ev.forwarded_from_id)
            keys.add(
                ("src", src) if src is not None
                else ("orig", ev.forwarded_from_channel_id, ev.forwarded_from_id)
            )
        else:
            keys.add(("src", ev.source_id))
    return keys


def _family(target_type: str) -> str:
    """Collapse target types to a family for conflict detection: ballistic is a
    specialization of missile, so the two never count as a source conflict."""
    return "missile" if target_type in ("missile", "ballistic") else target_type


def compute_fusion(events: Iterable[ThreatEvent]) -> FusionResult:
    """Derive corroboration, conflict, and fused confidence for a track.

    NOTE: this is the deliberately-simple skeleton version. The real fusion
    (time-windowed correlation, trust-weighting, spatial consistency, entity
    resolution across phrasings) lands once we have live channels and an eval
    set. The data model already carries everything that richer logic needs.
    """
    events = list(events)
    origins = _origin_keys(events)
    corroboration = max(1, len(origins))

    # "unknown" means the message stated NO target type (e.g. a terse
    # corroboration like "Бориспіль уважно") — it is not a competing claim,
    # so it must not count as disagreeing with a source that DID state one
    # (e.g. "shahed"). A real conflict is only 2+ distinct STATED FAMILIES:
    # "ballistic" is a specific kind of "missile", so one source saying
    # "8 балістичних ракет С-400" and another "8 ракет" describe the SAME salvo
    # at different specificity — NOT a disagreement. Collapse them to one family
    # before counting, else every ballistic salvo flags a false source conflict.
    claimed = {
        _family(ev.event_target_type) for ev in events
        if ev.event_target_type and ev.event_target_type != "unknown"
    }
    has_conflict = len(claimed) > 1

    if corroboration <= 1:
        base = 0.5
    elif corroboration == 2:
        base = 0.75
    else:
        base = 0.9
    if has_conflict:
        base -= 0.2

    return FusionResult(corroboration, has_conflict, round(max(0.1, base), 2))

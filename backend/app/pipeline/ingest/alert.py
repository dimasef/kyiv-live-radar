"""Official alert-channel ingest — separate from the spotter pipeline because it
needs none of the spotter context (district matcher, reply-threading, forward
attribution: this channel never reply-threads or reposts). Shares `_ingest_lock`
with the spotter path so the two can never race on the raw-message dedup guard.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from ...domain.alerts import AlertSignal, apply_alert_signal
from ...domain.incidents import end_active_incidents
from ...domain.tracking import close_all_active
from ...models import Notice, RawMessage
from ...parsing.alert_parser import parse_alert_message
from ..lock import _ingest_lock
from ..results import Broadcast


async def ingest_alert_message(
    session,
    *,
    text: str,
    when: datetime,
    source_id: int | None = None,
    message_id: int | None = None,
) -> list[Broadcast]:
    """Serialized entry point for the OFFICIAL alert channel. Shares `_ingest_lock`
    with the spotter path so the two can never race on the same raw-message dedup
    guard."""
    async with _ingest_lock:
        return await _alert_ingest_locked(session, text=text, when=when,
                                          source_id=source_id, message_id=message_id)


async def _alert_ingest_locked(
    session, *, text: str, when: datetime, source_id: int | None, message_id: int | None
) -> list[Broadcast]:
    # Deliberately NOT "raw storage first" here, unlike the spotter pipeline
    # (see ingest_message's docstring) — this channel's non-alert traffic is
    # bulk city news (infra updates, recaps), not spotter data worth growing
    # an eval set from, so a message that doesn't parse as a start/end is
    # dropped without ever touching raw_messages.
    if parse_alert_message(text) is None:
        return []

    if message_id is not None:
        dup = await session.scalar(
            select(RawMessage.id).where(
                RawMessage.source_id == source_id, RawMessage.message_id == message_id
            )
        )
        if dup is not None:
            return []

    raw = RawMessage(source_id=source_id, message_id=message_id, text=text, event_time=when)
    session.add(raw)
    await session.commit()

    return await process_parsed_alert(session, raw=raw, text=text, when=when, source_id=source_id)


async def process_parsed_alert(
    session, *, raw: RawMessage, text: str, when: datetime, source_id: int | None
) -> list[Broadcast]:
    """Parse -> apply an ALREADY-PERSISTED alert-channel raw message. Split
    out from `_alert_ingest_locked` so `reprocess.py` can replay stored
    alert-channel messages the same way it replays spotter ones. The
    `parsed is None` branch is now unreachable from live ingestion (see
    `_alert_ingest_locked`, which drops non-alert text before it's ever
    persisted) but stays live for `reprocess.py` replaying raw_messages rows
    stored before that filter existed."""
    parsed = parse_alert_message(text)
    raw.processed = True
    if parsed is None:
        await session.commit()
        return []

    signal = AlertSignal(
        scope=parsed.scope, action=parsed.action, when=when,
        provider="telegram", raw_id=raw.id,
    )
    alert = await apply_alert_signal(session, signal)
    await session.commit()
    if alert is None:  # idempotent no-op (already open / nothing to end)
        return []
    broadcasts: list[Broadcast] = [Broadcast("alert", alert=alert)]

    # A CITY alert ending is the end of the whole attack: close every open
    # track (reason='all_clear', same as a spotter відбій) and end every
    # active incident (ended_reason='alert_end'). This is naturally
    # idempotent alongside the spotter відбій path above — whichever lands
    # first does the real work; `alert is None` already returned early for a
    # repeat, and close_all_active/end_active_incidents are no-ops when
    # nothing is open — so an official + spotter відбій seconds apart dedupe
    # instead of double-firing.
    if parsed.action == "end" and parsed.scope == "city":
        closed_tracks = await close_all_active(session, when, "all_clear")
        broadcasts += [Broadcast("status", t) for t in closed_tracks]
        ended_incidents = await end_active_incidents(session, when, "alert_end")
        broadcasts += [Broadcast("attack", incident=inc) for inc in ended_incidents]
        # Surface the all-clear in the feed too (the banner alone is invisible
        # in the Стрічка подій). This "Відбій" card used to be raised by the
        # spotter відбій path, which no longer fires a full clear — the feed
        # card now comes from the authoritative official channel instead.
        notice = Notice(kind="clear", text=text, target_type="unknown",
                        source_id=source_id, event_time=when,
                        source_message_id=raw.message_id)
        session.add(notice)
        await session.commit()
        broadcasts.append(Broadcast("notice", notice=notice))

    return broadcasts

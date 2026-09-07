"""Official alert-channel ingest — separate from the spotter pipeline because it
needs none of the spotter context (district matcher, reply-threading, forward
attribution: this channel never reply-threads or reposts). Shares `ingest_lock`
with the spotter path so the two can never race on the raw-message dedup guard.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select

from ...domain.alerts import AlertSignal, apply_alert_signal
from ...domain.districts import resolve_region
from ...domain.incidents import end_active_incidents
from ...domain.tracking import close_all_active
from ...models import Notice, RawMessage
from ...parsing.alert_parser import parse_alert_message
from ...timeutil import naive
from ..lock import ingest_lock
from ..results import Broadcast

log = logging.getLogger("ingest")


async def ingest_alert_message(
    session,
    *,
    text: str,
    when: datetime,
    source_id: int | None = None,
    message_id: int | None = None,
    enforce_age: bool = False,
) -> list[Broadcast]:
    """Serialized entry point for the OFFICIAL alert channel. Shares `ingest_lock`
    with the spotter path so the two can never race on the same raw-message dedup
    guard."""
    async with ingest_lock:
        return await _alert_ingest_locked(session, text=text, when=when,
                                          source_id=source_id, message_id=message_id,
                                          enforce_age=enforce_age)


async def _alert_ingest_locked(
    session, *, text: str, when: datetime, source_id: int | None, message_id: int | None,
    enforce_age: bool = False,
) -> list[Broadcast]:
    # Deliberately NOT "raw storage first" here, unlike the spotter pipeline
    # (see ingest_message's docstring) — this channel's non-alert traffic is
    # bulk city news (infra updates, recaps), not spotter data worth growing
    # an eval set from, so a message that doesn't parse as a start/end is
    # dropped without ever touching raw_messages.
    if parse_alert_message(text) is None:
        return []

    raw = None
    if message_id is not None:
        raw = await session.scalar(
            select(RawMessage).where(
                RawMessage.source_id == source_id, RawMessage.message_id == message_id
            )
        )
    # A message we have already STORED is not a message we have already ACTED
    # on, and the difference is the whole reason this replays instead of
    # returning early. Every transition below is idempotent by construction
    # (domain/alerts.apply_alert_signal), so a repeat costs a parse and writes
    # nothing — while a pass that failed to write the first time (vetoed as
    # superseded, crashed mid-commit) repairs itself on the next reconnect
    # backfill. Live 2026-09-07: the 16:39 alert was backfilled at 17:46,
    # dropped by the age gate this replaced, and then unreachable forever —
    # its raw row existed, so every later backfill skipped it and Kyiv sat
    # painted clear through a red alert.
    if raw is None:
        raw = RawMessage(source_id=source_id, message_id=message_id, text=text, event_time=when)
        session.add(raw)
        await session.commit()

    return await process_parsed_alert(session, raw=raw, text=text, when=when,
                                      source_id=source_id, enforce_age=enforce_age)


async def _stood_down_since(session, raw: RawMessage, when: datetime) -> bool:
    """Whether a ВІДБІЙ later than this message has already been applied.

    The one gate a backfilled START has to pass. It used to be a plain age check
    (`is_late`), and that is what broke Kyiv on 2026-09-07: the 16:39 alert was
    still running when the listener reconnected at 17:46, and its start was
    thrown away for being 67 minutes old — leaving the capital painted clear
    through a red alert while every raion around it glowed.

    Age is the wrong question for this channel, and the channel's own rules say
    so: «Кожне нове повідомлення показує актуальний на цей момент вид і рівень
    загрози… нове повідомлення автоматично замінює попереднє» (post 20351). The
    newest announcement IS the current state however long ago it was posted.

    What must never be replayed is a start the siren has already OUTLIVED. That
    is the 2026-07-31 failure the age check was standing in for: the відбій
    (06:53) was ingested before the 05:59 start it belonged to, so the end
    no-op'd and the start then opened a phantom alert that hung on the banner
    for two hours. A later ВІДБІЙ is the only thing that invalidates a start —
    a later start does not, it is the same siren announcing a new level, and
    replaying both in order gives the true start time AND the current level.

    Reads the channel's own stored messages rather than the `alerts` table: an
    end that no-op'd (the 07-31 shape, nothing open to close) leaves no row
    behind, and that is exactly the case this has to catch.
    """
    rows = await session.execute(
        select(RawMessage.text)
        .where(
            RawMessage.source_id == raw.source_id,
            RawMessage.id != raw.id,
            RawMessage.processed.is_(True),
            RawMessage.event_time > naive(when),
        )
        .order_by(RawMessage.event_time)
        # A reconnect backfill spans `telegram_backfill` messages per channel,
        # so "later than this one" is a handful; the cap only keeps a reprocess
        # of deep history from reading a year of them.
        .limit(200)
    )
    for (text,) in rows:
        parsed = parse_alert_message(text or "")
        if parsed is not None and parsed.action == "end":
            return True
    return False


async def process_parsed_alert(
    session, *, raw: RawMessage, text: str, when: datetime, source_id: int | None,
    enforce_age: bool = False,
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

    if enforce_age and parsed.action == "start" and await _stood_down_since(session, raw, when):
        log.info("ignoring superseded alert start (raw %s, posted %s) — a later "
                 "відбій is already applied", raw.id, when)
        await session.commit()
        return []

    # An alert names no district, so its region can only come from the channel
    # that announced it (`sources.region`) — the same fallback a district-less
    # spotter message uses.
    region = await resolve_region(session, [], source_id)
    signal = AlertSignal(
        scope=parsed.scope, action=parsed.action, when=when, region=region,
        provider="telegram", raw_id=raw.id,
        level=parsed.level, threat=parsed.threat,
    )
    outcome = await apply_alert_signal(session, signal)
    await session.commit()
    if outcome is None:  # idempotent no-op (already open at this level / nothing to end)
        return []
    alert = outcome.alert
    broadcasts: list[Broadcast] = [Broadcast("alert", alert=alert)]

    # The level moved inside a running alert — no new siren, but the feed must
    # say so: «Дронова небезпека» becoming «Ракетна загроза» is the single most
    # consequential thing this channel publishes, and the banner alone is one
    # line that scrolls past. The card carries the channel's own words.
    if outcome.kind == "escalated":
        notice = Notice(kind="alert_level", text=text, target_type="unknown",
                        source_id=source_id, event_time=when,
                        source_message_id=raw.message_id)
        session.add(notice)
        await session.commit()
        broadcasts.append(Broadcast("notice", notice=notice))
        return broadcasts

    # A CITY alert ending is the end of the whole attack: close every open
    # track (reason='all_clear', same as a spotter відбій) and end every
    # active incident (ended_reason='alert_end'). This is naturally
    # idempotent alongside the spotter відбій path above — whichever lands
    # first does the real work; `alert is None` already returned early for a
    # repeat, and close_all_active/end_active_incidents are no-ops when
    # nothing is open — so an official + spotter відбій seconds apart dedupe
    # instead of double-firing.
    if parsed.action == "end" and parsed.scope == "city":
        # The siren speaks for ITS OWN region only — a track in another one it
        # never covered stays open until that region clears it. Read off the
        # alert rather than assumed, which is the whole point of `Alert.region`.
        closed_tracks = await close_all_active(session, when, "all_clear",
                                               region=alert.region)
        broadcasts += [Broadcast("status", t) for t in closed_tracks]
        ended_incidents = await end_active_incidents(session, when, "alert_end",
                                                     region=alert.region)
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

"""Shared filter + row serialization for the /raw_messages debug endpoints
(list, count, export). Keeping the WHERE-building and labeling in one place is
what guarantees an export represents exactly what the operator was looking at
— a filter that behaved differently between the list and the export would make
the exported file silently misrepresent the on-screen view."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import exists, or_, select

from ..feeds.common import build_matcher
from ..models import Notice, RawMessage, ThreatEvent
from ..parsing.alert_parser import parse_alert_message
from ..schemas import RawEventLinkOut, RawMessageOut
from .raw_codes import parse_codes
from .raw_diagnosis import diagnose


def _alert_label(text: str) -> str:
    """Outcome label for an alert-role channel message (КМДА). The spotter
    `diagnose()` mislabels these (a shelter-map URL reads as реклама/донат) — an
    official channel goes through the ALERT parser instead, so re-derive with it."""
    parsed = parse_alert_message(text)
    if parsed is None:
        return "не про загрозу"
    return "офіційна тривога" if parsed.action == "start" else "офіційний відбій"


def apply_raw_filters(
    stmt,
    *,
    q: Optional[str] = None,
    outcome: Optional[str] = None,
    llm: Optional[str] = None,
    source_id: Optional[int] = None,
):
    """Apply the /raw_messages filter set (channel, text/code search, outcome,
    LLM) to a select over RawMessage — pagination (before_id/limit) is the
    caller's concern, not a filter, so it stays out of here."""
    # A raw message "became a sighting"/"became a notice" iff a ThreatEvent/
    # Notice recorded the same (source_id, source_message_id) pair — the same
    # EXISTS drives both the outcome filter here and the per-row labeling in
    # serialize_raw_rows, so filtering and labels never disagree. Notices
    # predating source_message_id (NULL) never match, same as any raw message
    # with no Telegram id.
    became_event = exists().where(
        ThreatEvent.source_id == RawMessage.source_id,
        ThreatEvent.source_message_id == RawMessage.message_id,
    )
    became_notice = exists().where(
        Notice.source_id == RawMessage.source_id,
        Notice.source_message_id == RawMessage.message_id,
    )

    if source_id is not None:
        stmt = stmt.where(RawMessage.source_id == source_id)

    codes = parse_codes(q) if q else []
    if codes:
        # A code never appears in a message's own text, so a recognized code
        # replaces substring search entirely rather than combining with it.
        code_filters = []
        for kind, num in codes:
            if kind == "T":
                code_filters.append(
                    exists().where(
                        ThreatEvent.source_id == RawMessage.source_id,
                        ThreatEvent.source_message_id == RawMessage.message_id,
                        ThreatEvent.threat_id == num,
                    )
                )
            elif kind == "M":
                code_filters.append(
                    exists().where(
                        ThreatEvent.source_id == RawMessage.source_id,
                        ThreatEvent.source_message_id == RawMessage.message_id,
                        ThreatEvent.id == num,
                    )
                )
            elif kind == "N":
                code_filters.append(
                    exists().where(
                        Notice.source_id == RawMessage.source_id,
                        Notice.source_message_id == RawMessage.message_id,
                        Notice.id == num,
                    )
                )
        stmt = stmt.where(or_(*code_filters))
    elif q:
        stmt = stmt.where(RawMessage.text.ilike(f"%{q}%"))

    if outcome == "event":
        stmt = stmt.where(became_event | became_notice)
    elif outcome == "suppressed":
        stmt = stmt.where(~became_event, ~became_notice)
    if llm == "yes":
        stmt = stmt.where(RawMessage.llm_attempted.is_(True))
    elif llm == "no":
        stmt = stmt.where(RawMessage.llm_attempted.is_(False))
    return stmt


async def serialize_raw_rows(session, rows: list[RawMessage]) -> list[RawMessageOut]:
    """Turn RawMessage rows into RawMessageOut, resolving each one's real
    pipeline outcome — authoritative 'подія'/'нотіс' when a ThreatEvent/Notice
    actually matched (keyed by (source_id, message_id), since a Telegram
    message_id is only unique within its own channel), a best-effort re-derived
    label otherwise (see raw_diagnosis.diagnose)."""
    message_ids = [r.message_id for r in rows if r.message_id is not None]
    events_by_key: dict[tuple[int | None, int], list[tuple[int, int]]] = {}
    notice_by_key: dict[tuple[int | None, int], int] = {}
    if message_ids:
        ev_rows = await session.execute(
            select(
                ThreatEvent.source_id, ThreatEvent.source_message_id,
                ThreatEvent.threat_id, ThreatEvent.id,
            ).where(ThreatEvent.source_message_id.in_(message_ids))
        )
        for source_id, source_message_id, threat_id, event_id in ev_rows:
            events_by_key.setdefault((source_id, source_message_id), []).append(
                (threat_id, event_id)
            )
        n_rows = await session.execute(
            select(Notice.source_id, Notice.source_message_id, Notice.id).where(
                Notice.source_message_id.in_(message_ids)
            )
        )
        for source_id, source_message_id, notice_id in n_rows:
            notice_by_key[(source_id, source_message_id)] = notice_id

    matcher = await build_matcher()
    items: list[RawMessageOut] = []
    for r in rows:
        key = (r.source_id, r.message_id) if r.message_id is not None else None
        events = events_by_key.get(key, []) if key else []
        notice_id = notice_by_key.get(key) if key else None
        if events:
            row_outcome = "подія"
        elif notice_id is not None:
            row_outcome = "нотіс"
        elif r.source is not None and r.source.role == "alert":
            row_outcome = _alert_label(r.text)
        else:
            row_outcome = diagnose(r.text, matcher)
        items.append(
            RawMessageOut(
                id=r.id,
                source_id=r.source_id,
                source_name=r.source.name if r.source else None,
                message_id=r.message_id,
                text=r.text,
                event_time=r.event_time,
                forwarded_from_id=r.forwarded_from_id,
                reply_to_message_id=r.reply_to_message_id,
                processed=r.processed,
                outcome=row_outcome,
                events=[RawEventLinkOut(threat_id=t, event_id=e) for t, e in events],
                notice_id=notice_id,
                llm_attempted=r.llm_attempted,
                llm_input_tokens=r.llm_input_tokens,
                llm_output_tokens=r.llm_output_tokens,
                llm_cost_usd=r.llm_cost_usd,
                llm_response=r.llm_response,
            )
        )
    return items

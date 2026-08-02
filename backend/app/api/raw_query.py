"""Shared filter + row serialization for the /raw_messages debug endpoints
(list, count, export). Keeping the WHERE-building and labeling in one place is
what guarantees an export represents exactly what the operator was looking at
— a filter that behaved differently between the list and the export would make
the exported file silently misrepresent the on-screen view."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import exists, or_, select, tuple_

from ..feeds.common import build_matcher
from ..models import District, Notice, RawMessage, Threat, ThreatEvent
from ..parsing import ParseResult
from ..parsing.alert_parser import parse_alert_message
from ..schemas import RawEventLinkOut, RawMessageOut, RawParsedOut
from .raw_codes import parse_codes
from .raw_diagnosis import diagnose


@dataclass(frozen=True)
class _EventRow:
    """One ThreatEvent row of the bulk lookup below, named so the unpacking
    doesn't degrade into positional tuple indexing as columns are added."""

    threat_id: int
    event_id: int
    target_type: str | None
    district_id: int | None
    district_name: str | None
    decision_source: str | None


@dataclass(frozen=True)
class _ThreatState:
    incident_id: int | None
    corroboration_count: int | None
    confidence: float | None
    status: str | None
    closed_reason: str | None


def _event_link(ev: _EventRow, state: _ThreatState | None) -> RawEventLinkOut:
    return RawEventLinkOut(
        threat_id=ev.threat_id,
        event_id=ev.event_id,
        target_type=ev.target_type,
        district_id=ev.district_id,
        district_name=ev.district_name,
        decision_source=ev.decision_source,
        incident_id=state.incident_id if state else None,
        corroboration_count=state.corroboration_count if state else None,
        confidence=state.confidence if state else None,
        threat_status=state.status if state else None,
        threat_closed_reason=state.closed_reason if state else None,
    )


def _parsed_out(parsed: ParseResult) -> RawParsedOut:
    return RawParsedOut(
        target_type=parsed.target_type,
        status=parsed.status,
        target_count=parsed.target_count,
        confidence=parsed.confidence,
        matched=parsed.matched,
        district_ids=[h.district_id for h in parsed.districts],
        district_names=[h.name for h in parsed.districts],
        citywide=parsed.citywide,
        directional=parsed.directional,
        target_pulse=parsed.target_pulse,
        impact=parsed.impact,
        origin_key=parsed.origin_key,
    )


async def _reply_parent_ids(session, rows: list[RawMessage]) -> dict[tuple, int]:
    """(source_id, message_id) -> raw_messages.id, for every message some row in
    this page replies to. A reply whose parent is MISSING from the result is one
    the pipeline couldn't thread — either never stored, or (the 2026-08-02 case)
    stored only after the reply itself."""
    keys = [
        (r.source_id, r.reply_to_message_id)
        for r in rows
        if r.reply_to_message_id is not None and r.source_id is not None
    ]
    if not keys:
        return {}
    found = await session.execute(
        select(RawMessage.source_id, RawMessage.message_id, RawMessage.id).where(
            tuple_(RawMessage.source_id, RawMessage.message_id).in_(keys)
        )
    )
    return {(source_id, message_id): raw_id for source_id, message_id, raw_id in found}


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
    q: str | None = None,
    outcome: str | None = None,
    llm: str | None = None,
    source_id: int | None = None,
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
    events_by_key: dict[tuple[int | None, int], list[_EventRow]] = {}
    notice_by_key: dict[tuple[int | None, int], tuple[int, str]] = {}
    # threat_id -> lifecycle + fusion state of the owning track, so each event
    # chip in the admin /raw view carries what the public feed dropped.
    threat_state: dict[int, _ThreatState] = {}
    if message_ids:
        ev_rows = await session.execute(
            select(
                ThreatEvent.source_id, ThreatEvent.source_message_id,
                ThreatEvent.threat_id, ThreatEvent.id, ThreatEvent.event_target_type,
                ThreatEvent.district_id, District.name_uk, ThreatEvent.decision_source,
            )
            .outerjoin(District, ThreatEvent.district_id == District.id)
            .where(ThreatEvent.source_message_id.in_(message_ids))
        )
        for source_id, source_message_id, *rest in ev_rows:
            events_by_key.setdefault((source_id, source_message_id), []).append(
                _EventRow(*rest)
            )
        n_rows = await session.execute(
            select(Notice.source_id, Notice.source_message_id, Notice.id, Notice.kind).where(
                Notice.source_message_id.in_(message_ids)
            )
        )
        for source_id, source_message_id, notice_id, kind in n_rows:
            notice_by_key[(source_id, source_message_id)] = (notice_id, kind)

        threat_ids = {ev.threat_id for links in events_by_key.values() for ev in links}
        if threat_ids:
            t_rows = await session.execute(
                select(
                    Threat.id, Threat.incident_id,
                    Threat.corroboration_count, Threat.confidence,
                    Threat.status, Threat.closed_reason,
                ).where(Threat.id.in_(threat_ids))
            )
            for tid, *state in t_rows:
                threat_state[tid] = _ThreatState(*state)

    reply_parents = await _reply_parent_ids(session, rows)
    # On THIS session: the diagnosis now runs for every row, so the gazetteer it
    # matches against must be the one this request reads (build_matcher's own
    # rule for request handlers) rather than a second connection's.
    matcher = await build_matcher(session)
    items: list[RawMessageOut] = []
    for r in rows:
        key = (r.source_id, r.message_id) if r.message_id is not None else None
        events = events_by_key.get(key, []) if key else []
        notice = notice_by_key.get(key) if key else None
        is_alert_channel = r.source is not None and r.source.role == "alert"
        # The diagnosis is re-derived for EVERY row, not just unexplained ones:
        # its `parsed` snapshot is what makes an export self-explanatory, and
        # `outcome` still prefers the authoritative event/notice when there is
        # one. Alert-channel rows go through their own parser instead.
        diag = None if is_alert_channel else diagnose(r.text, matcher)
        if events:
            row_outcome, suppressed_by = "подія", None
        elif notice is not None:
            row_outcome, suppressed_by = "нотіс", None
        elif diag is None:
            row_outcome, suppressed_by = _alert_label(r.text), None
        else:
            row_outcome, suppressed_by = diag.label, diag.flag
        items.append(
            RawMessageOut(
                id=r.id,
                source_id=r.source_id,
                source_name=r.source.name if r.source else None,
                source_role=r.source.role if r.source else None,
                message_id=r.message_id,
                text=r.text,
                event_time=r.event_time,
                ingested_at=r.ingested_at,
                forwarded_from_id=r.forwarded_from_id,
                reply_to_message_id=r.reply_to_message_id,
                reply_parent_raw_id=reply_parents.get((r.source_id, r.reply_to_message_id)),
                processed=r.processed,
                outcome=row_outcome,
                suppressed_by=suppressed_by,
                parsed=_parsed_out(diag.parsed) if diag is not None else None,
                events=[_event_link(ev, threat_state.get(ev.threat_id)) for ev in events],
                notice_id=notice[0] if notice else None,
                notice_kind=notice[1] if notice else None,
                llm_attempted=r.llm_attempted,
                llm_input_tokens=r.llm_input_tokens,
                llm_output_tokens=r.llm_output_tokens,
                llm_cost_usd=r.llm_cost_usd,
                llm_response=r.llm_response,
                triage_state=r.triage_state,
                triage_action=r.triage_action,
            )
        )
    return items

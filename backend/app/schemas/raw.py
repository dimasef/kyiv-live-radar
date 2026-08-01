"""Raw-message debug views: rows, pages, counts, export and LLM usage."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator

from ..models import TargetType
from .base import _as_utc


class RawEventLinkOut(BaseModel):
    """One ThreatEvent a raw message produced — the same T{threat_id}/
    M{event_id} pair shown as a dev badge in the feed. A single raw message
    can produce SEVERAL (e.g. an untyped "дорозвідка" closing multiple open
    tracks at once), hence a list on RawMessageOut rather than one pair."""

    threat_id: int
    event_id: int
    # The target type stamped on this event ('shahed'|'ballistic'|... or
    # 'unknown'/None) — surfaced in /raw so an admin sees what type the message
    # was classified as, not just that it produced an event.
    target_type: TargetType | None = None
    # Fusion/track state of the OWNING threat (not the single event) — the
    # public feed no longer shows these, so the admin /raw view carries them
    # instead: which attack the track rolled into, how many independent sources
    # corroborate it, and its fused 0..1 confidence. None when the threat row
    # is gone (event orphaned) or the track carries no incident.
    incident_id: int | None = None
    corroboration_count: int | None = None
    confidence: float | None = None


class RawMessageOut(BaseModel):
    """One verbatim ingested message plus a debug diagnosis of what the
    pipeline did with it — see GET /raw_messages. `outcome`/`events`/
    `notice_id` are authoritative when a real ThreatEvent/Notice matched
    ('подія'/'нотіс'); a best-effort re-derived label otherwise (see
    api/raw_diagnosis.py)."""

    id: int
    source_id: int | None = None
    source_name: str | None = None
    message_id: int | None = None
    text: str
    event_time: datetime
    forwarded_from_id: int | None = None
    reply_to_message_id: int | None = None
    processed: bool
    outcome: str
    events: list[RawEventLinkOut] = []
    notice_id: int | None = None
    # Whether the LLM fallback was called for this message — None for rows
    # ingested before this was tracked (genuinely unknown, not "no").
    llm_attempted: bool | None = None
    # Token usage/cost for that call — set together with llm_attempted=True
    # whenever it actually completed; None otherwise.
    llm_input_tokens: int | None = None
    llm_output_tokens: int | None = None
    llm_cost_usd: float | None = None
    # The full structured LLM response (district_ids + triage category/surface/
    # summary) — present only when the LLM produced usable JSON; None otherwise.
    # Collected for /raw audit; nothing in the product routes on it yet.
    llm_response: dict | None = None
    # Async-triage bookkeeping (see TRIAGE_STATES/TRIAGE_ACTIONS) — where the
    # message went in the triage queue and what routing did with its verdict.
    # NULL for messages the triage engine never enqueued.
    triage_state: str | None = None
    triage_action: str | None = None

    _tz_raw = field_validator("event_time", mode="before")(_as_utc)


class RawMessagesPage(BaseModel):
    """Cursor-paginated page of raw messages, newest first."""

    items: list[RawMessageOut]
    # Pass as `before_id` to fetch the next page; None once there's no more.
    next_before_id: int | None = None


class RawSourceOut(BaseModel):
    """One monitored channel, for the /raw channel filter dropdown."""

    id: int
    name: str


class RawCountOut(BaseModel):
    """How many raw messages match the current /raw filter set."""

    count: int


class RawExportOut(BaseModel):
    """All raw messages matching the current filter (up to the export cap),
    for offline analysis — see GET /raw_messages/export. `truncated` flags a
    partial export so it's never mistaken for the complete set."""

    messages: list[RawMessageOut]
    truncated: bool


class RawLlmStatsOut(BaseModel):
    """Aggregate LLM fallback usage across all raw messages — see
    GET /raw_messages/llm_stats."""

    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float

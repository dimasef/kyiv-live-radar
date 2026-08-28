"""Admin console: moderation inputs, coverage gaps, corrections, reprocess."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator

from ..models import CorrectionKind, NoticeKind, TargetType
from .base import _as_utc
from .situation import AlertOut, IncidentOut
from .threats import ThreatOut


class RawNoticeIn(BaseModel):
    """POST /admin/raw_messages/{id}/notice — publish a message the parser left
    out as a feed notice (a forecast, an all-clear, a situation summary).

    `text` defaults to the message's own text: most of the time the spotter
    already said it well, and retyping it invites drift from the original."""

    kind: NoticeKind
    text: str | None = None


class ThreatTypeIn(BaseModel):
    """PATCH /admin/threats/{id} — admin retype of a track's target."""

    target_type: TargetType


class EventDistrictIn(BaseModel):
    """PATCH /admin/events/{id} — admin fixes a mislocated sighting."""

    district_id: int


class EventTrackIn(BaseModel):
    """PATCH /admin/events/{id}/threat — admin regroups a sighting.

    `threat_id` names the track to move it ONTO; None splits it out onto a track
    of its own. Both are the same operation from tracking's point of view — it
    grouped this sighting wrong, and the fix is to say where it belongs."""

    threat_id: int | None = None


class RegroupOut(BaseModel):
    """PATCH /admin/events/{id}/threat — BOTH tracks the move touched.

    A regroup always changes two tracks, and the admin view has to update both:
    returning only the destination left the source still advertising a sighting
    it no longer owns."""

    event_id: int
    # The track the sighting now lives on (newly created, when it was a split).
    threat: ThreatOut
    # The track it came from — still a row even when the move emptied and
    # dismissed it, so the caller can redraw or drop it.
    source_threat: ThreatOut


class DismissedOut(BaseModel):
    """GET /admin/dismissed — recently admin-cancelled entities, for the
    'Повернути' (restore) list in the admin panel."""

    threats: list[ThreatOut] = []
    incidents: list[IncidentOut] = []
    alerts: list[AlertOut] = []


class CoverageGapOut(BaseModel):
    """GET /admin/coverage_gaps — a message the parser couldn't localize that
    still names something (likely a missing gazetteer entry)."""

    raw_message_id: int
    text: str
    event_time: datetime
    source_name: str | None = None
    detected_target_type: TargetType
    detected_status: str
    # The unknown place-name words this row was admitted for — so the operator
    # sees WHICH word to look up, not just that the message failed.
    candidates: list[str] = []

    _tz_gap = field_validator("event_time", mode="before")(_as_utc)


class CoverageCandidateOut(BaseModel):
    """GET /admin/coverage_candidates — one unknown place-name, with how often
    it occurred in the scanned window. The ranked gazetteer work-list."""

    name: str
    count: int
    example_text: str
    example_raw_message_id: int


class CorrectionOut(BaseModel):
    """GET /admin/corrections — a harvested correction plus whether the CURRENT
    parser already agrees (so the admin sees which mistakes are retired)."""

    id: int
    raw_message_id: int | None = None
    text: str
    kind: CorrectionKind
    expected: dict = {}
    origin: str
    created_at: datetime
    resolved: bool  # current parser now matches the correction

    _tz_corr = field_validator("created_at", mode="before")(_as_utc)


class ReprocessDayOut(BaseModel):
    date: str
    target_count: int
    track_count: int


class ReprocessSummaryOut(BaseModel):
    """Snapshot used to diff a reprocess: totals + recent per-day target counts
    (where the phantom-count inflation like the 23.07 '432 цілі' shows up)."""

    tracks: int
    events: int
    incidents: int
    days: list[ReprocessDayOut] = []


class ReprocessPreviewOut(BaseModel):
    """GET /admin/reprocess/preview — pre-flight scope, no mutation."""

    raw_messages: int  # everything stored, whatever the requested scope
    current: ReprocessSummaryOut
    attack_active: bool  # refuse-by-default guard: don't rebuild mid-attack
    # With `?last=N`: how many messages that tail ACTUALLY replays (N widened so
    # no track/alert is cut in half — see pipeline/reprocess.scope_cutoff) and
    # the instant it starts from. Both None when rebuilding everything.
    scope_messages: int | None = None
    scope_from: datetime | None = None


class ReprocessApplyIn(BaseModel):
    no_llm: bool = True  # match the boot path; True is fast + free
    force: bool = False  # override the mid-attack guard
    # Rebuild only the last N stored messages, keeping older history. None =
    # everything (the old behaviour).
    last: int | None = None


class ReprocessResultOut(BaseModel):
    """POST /admin/reprocess/apply — before/after diff + raw replay counts."""

    before: ReprocessSummaryOut
    after: ReprocessSummaryOut
    result: dict

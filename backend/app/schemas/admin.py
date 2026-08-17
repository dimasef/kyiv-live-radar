"""Admin console: moderation inputs, coverage gaps, corrections, reprocess."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

from ..models import CorrectionKind, TargetType
from .base import _as_utc
from .situation import AlertOut, IncidentOut
from .threats import ThreatOut


class ThreatTypeIn(BaseModel):
    """PATCH /admin/threats/{id} — admin retype of a track's target."""

    target_type: Literal["shahed", "jet_drone", "missile", "ballistic", "unknown"]


class EventDistrictIn(BaseModel):
    """PATCH /admin/events/{id} — admin fixes a mislocated sighting."""

    district_id: int


class DismissedOut(BaseModel):
    """GET /admin/dismissed — recently admin-cancelled entities, for the
    'Повернути' (restore) list in the admin panel."""

    threats: list[ThreatOut] = []
    incidents: list[IncidentOut] = []
    alerts: list[AlertOut] = []


class CoverageGapOut(BaseModel):
    """GET /admin/coverage_gaps — a threat-flavored message the parser couldn't
    localize (likely a missing gazetteer entry)."""

    raw_message_id: int
    text: str
    event_time: datetime
    source_name: str | None = None
    detected_target_type: TargetType
    detected_status: str

    _tz_gap = field_validator("event_time", mode="before")(_as_utc)


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

    raw_messages: int
    current: ReprocessSummaryOut
    attack_active: bool  # refuse-by-default guard: don't rebuild mid-attack


class ReprocessApplyIn(BaseModel):
    no_llm: bool = True  # match the boot path; True is fast + free
    force: bool = False  # override the mid-attack guard


class ReprocessResultOut(BaseModel):
    """POST /admin/reprocess/apply — before/after diff + raw replay counts."""

    before: ReprocessSummaryOut
    after: ReprocessSummaryOut
    result: dict

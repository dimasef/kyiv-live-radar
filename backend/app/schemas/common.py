"""Districts and feed sources — the reference data other schemas point at."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..models import Region, SourceRole
from .base import _as_utc


class DistrictOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name_uk: str
    name_en: str
    lat: float
    lon: float
    aliases: list[str] = []
    region: Region = "kyiv"


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_key: str
    name: str
    trust_weight: float


class SourceStatsOut(BaseModel):
    """Per-source quality signals, computed on-demand (JOIN by source_id) over a
    recent window — see app/api/source_stats.py. Rates are None when there's no
    denominator (e.g. llm_fallback_rate before any row had llm_attempted set)."""

    messages_total: int
    messages_processed: int
    events_produced: int
    llm_fallback_rate: float | None
    coverage_rate: float | None
    correction_rate: float | None
    conflict_share: float | None
    quality_score: float | None  # 0..100, informational (does NOT feed fusion)
    last_message_at: datetime | None


class SourceAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_key: str
    name: str
    subscribe_ref: str | None
    role: SourceRole
    region: Region
    is_active: bool
    trust_weight: float
    last_listener_error: str | None
    created_at: datetime | None
    stats: SourceStatsOut

    _tz_source = field_validator("created_at", mode="before")(_as_utc)


class SourceIn(BaseModel):
    """Add (or reactivate) a channel from the admin console."""

    subscribe_ref: str = Field(min_length=1, max_length=200)
    name: str | None = Field(default=None, max_length=120)
    role: Literal["spotter", "alert"] = "spotter"
    # Fallback region for this channel's district-less messages (a «Відбій» has
    # no place to read a region off) — see models.Source.region.
    region: Region = "kyiv"
    trust_weight: float = 1.0


class SourceUpdateIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    role: Literal["spotter", "alert"] | None = None
    region: Region | None = None
    trust_weight: float | None = None
    is_active: bool | None = None


class SourceDeleteOut(BaseModel):
    """What a hard-delete removed — surfaced so the admin sees the blast radius."""

    name: str
    raw_messages: int
    events: int
    notices: int
    threats_deleted: int
    incidents_deleted: int

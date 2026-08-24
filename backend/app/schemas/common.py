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


class SourceLinkOut(BaseModel):
    """One channel we read, for public attribution (the map legend's «Джерела»).

    Deliberately carries no `trust_weight`: that internal fusion knob would read
    publicly as our rating of a volunteer channel (admins get it via
    `SourceAdminOut`).

    `url` is None for anything that is not a plain public @username — a private
    channel's invite link must never be republished, and a numeric channel id
    has no public page to point at. Such a source is still listed by name;
    credit is owed either way.
    """

    id: int
    name: str
    role: SourceRole
    region: Region
    url: str | None


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
    # NULL = the global settings default (see Source.type_inherit_minutes).
    type_inherit_minutes: int | None
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
    # 0 disables inheritance for this channel entirely; the upper bound keeps a
    # typo ("300") from typing a whole night off one stale mention.
    type_inherit_minutes: int | None = Field(default=None, ge=0, le=120)
    is_active: bool | None = None


class SourceDeleteOut(BaseModel):
    """What a hard-delete removed — surfaced so the admin sees the blast radius."""

    name: str
    raw_messages: int
    events: int
    notices: int
    threats_deleted: int
    incidents_deleted: int

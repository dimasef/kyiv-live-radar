"""GET /sync — what a reconnecting client needs to catch up."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from .common import SourceLinkOut
from .situation import AlertOut, AxisOut, IncidentOut, NoticeOut
from .threats import FeedEntryOut, ThreatOut
from .ws import WSMessage
from .zones import AlertZoneOut


class SyncSnapshotOut(BaseModel):
    """Every slice `hydrate()` fetches, in one body — the same bytes the ten
    endpoints serve, spliced from the read cache."""

    threats: list[ThreatOut]
    incidents: list[IncidentOut]
    recent_incidents: list[IncidentOut]
    axes: list[AxisOut]
    alerts: list[AlertOut]
    zones: list[AlertZoneOut]
    events: list[FeedEntryOut]
    notices: list[NoticeOut]
    sources: list[SourceLinkOut]
    server_time: datetime
    feed_ok: bool | None = None


class SyncOut(BaseModel):
    # current: the client missed nothing. delta: apply `frames` in order, exactly
    # as if they had arrived live. full: replace every slice from `snapshot`
    # (another server process, or too long away for the frame history).
    status: Literal["current", "delta", "full"]
    epoch: int
    seq: int
    frames: list[WSMessage] = []
    snapshot: SyncSnapshotOut | None = None

"""Result objects passed from the ingest pipeline to its consumers
(broadcast, sweeper)."""

from __future__ import annotations

from dataclasses import dataclass

from ..models import Alert, Incident, Notice, Threat, ThreatAxis, ThreatEvent


@dataclass
class Broadcast:
    type: str  # 'event' | 'status' | 'notice' | 'alert' | 'attack' | 'axis'
    threat: Threat | None = None
    event: ThreatEvent | None = None
    notice: "Notice | None" = None
    alert: "Alert | None" = None
    incident: "Incident | None" = None
    axis: "ThreatAxis | None" = None

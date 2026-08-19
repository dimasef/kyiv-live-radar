"""Air-raid alert zones — the read-only siren-state layer (see
app/domain/alert_zones.py). Geometry is served separately, verbatim from the
data file, so it has no schema here."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator

from .base import _as_utc


class AlertZoneOut(BaseModel):
    """One raion's current siren state."""

    zone_id: str
    name_uk: str
    oblast: str
    alert: bool
    # When this state began, per the provider. NULL when it never reported a
    # change for this zone — the UI then shows the state without a duration.
    changed_at: datetime | None = None
    # True when the provider has been unreachable long enough that this state
    # can no longer be vouched for. The client must grey the layer out, NOT
    # render `alert=False` as an all-clear.
    stale: bool = False

    _tz_changed_at = field_validator("changed_at", mode="before")(_as_utc)

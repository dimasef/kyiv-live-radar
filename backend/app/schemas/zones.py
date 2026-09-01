"""Air-raid alert zones — the read-only siren-state layer (see
app/domain/alert_zones.py). Geometry is served separately, verbatim from the
data file, so it has no schema here."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator

from ..models import Region
from .base import _as_utc


class AlertZoneOut(BaseModel):
    """One raion's current siren state."""

    zone_id: str
    name_uk: str
    oblast: str
    # Which watched region's map this raion paints on. `oblast` is the
    # provider's display string; this is the id the rest of the app filters by,
    # so the client narrows the layer to the regions the reader follows without
    # keeping its own copy of the oblast→region table.
    region: Region
    alert: bool
    # When this state began, per the provider. NULL when it never reported a
    # change for this zone — the UI then shows the state without a duration.
    changed_at: datetime | None = None
    # True when the provider has been unreachable long enough that this state
    # can no longer be vouched for. The client must grey the layer out, NOT
    # render `alert=False` as an all-clear.
    stale: bool = False

    _tz_changed_at = field_validator("changed_at", mode="before")(_as_utc)


class AlertZoneAtOut(BaseModel):
    """Which raion a point falls in — the answer to "what is MY zone?".

    Served instead of letting the client resolve it against the geometry file:
    the polygons are ~76 KB and only downloaded when the reader turns the layer
    on, but every reader needs their own raion for the banner.
    """

    zone_id: str
    name_uk: str
    oblast: str
    region: Region

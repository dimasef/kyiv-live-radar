"""What a strike did to a raion — served only to vouched accounts.

Its own module rather than a class in `threats.py`: an aftermath report is not a
threat and shares no field with one (no target type, no count, no lifecycle, no
events), and the file boundary is the cheapest reminder of that when the next
person looks for somewhere to put a related model.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from ..models import AftermathCategory, Region
from .base import _as_utc


class AftermathOut(BaseModel):
    """One report, one raion. Everything here is already visible to the caller
    by the time they can call this route (see api/public/threats.py::aftermath),
    so nothing is withheld the way `IncidentOut` withholds an impact count — the
    withholding happens at the door, not per field."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    district_id: int
    # Denormalized so the map can place the marker without a second lookup —
    # the same convention `ThreatEventOut` follows for a sighting.
    district_name: str | None = None
    lat: float | None = None
    lon: float | None = None
    region: Region
    reported_at: datetime
    # One or more, ordered least → most consequential (domain/aftermath.py), so
    # the client reads the marker's label off the LAST element rather than
    # re-deriving an order the server already owns.
    categories: list[AftermathCategory] = []
    # The original message. The layer's readers are accounts an operator
    # vouched for by hand, and a category alone cannot answer "is this marker
    # right?" — the text is what makes a wrong one recognisable.
    text: str = ""
    source_id: int | None = None
    source_name: str | None = None

    _tz_reported_at = field_validator("reported_at", mode="before")(_as_utc)

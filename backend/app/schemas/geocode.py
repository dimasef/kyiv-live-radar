"""Address search results (see app/geocoding.py).

Nothing is stored — the reader types, picks a suggestion, and the map moves.
The point never reaches the server until they confirm a home, which goes
through the existing home endpoints.
"""

from __future__ import annotations

from pydantic import BaseModel

from ..models import GeocodeSource


class GeocodeHitOut(BaseModel):
    """One place the reader could mean."""

    # What identifies the place ("вулиця Хрещатик, 22"), and where it sits
    # ("Печерський район, Київ"). Split rather than one line so the list can
    # weight them differently — the second is context, not the answer.
    label: str
    sublabel: str | None = None
    lat: float
    lon: float
    # Which tier answered. A gazetteer hit is a settlement's centre and an OSM
    # one can be an exact address; the reader is told which they are looking at
    # because it changes how much they should trust the pin before confirming.
    source: GeocodeSource

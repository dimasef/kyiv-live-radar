"""Air-raid alert zones — the raions whose siren state the map paints.

This is a DIFFERENT layer from `Alert` (the official Kyiv city/oblast siren the
radar itself tracks, still fed by Telegram). It is read-only situational
context: an external provider tells us which raions of Київщина and Чернігівщина
are currently under alert, and the map colours them. Nothing here opens or
closes a track, an incident or an `Alert` row — if the provider dies, this layer
goes stale and everything else carries on.

State is deliberately NOT stored. The provider reports the instant each raion
last changed, so a restart re-learns both the state and how long it has held —
there is nothing a table would add.

Zone geometry lives in `app/data/alert_zones.json`, fetched once by
`scripts/fetch_alert_zones.py` (same one-off pattern as boundaries.json).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..regions import REGION_SPECS, SPEC_BY_ID, Region

# Oblast names exactly as the provider spells them, taken from the region
# registry. Matching on the name rather than on the provider's numeric key: the
# key is an implementation detail of one upstream source, the name is what every
# source and the UI agree on. Unpacked positionally so a registry edit that
# changes a region's oblast count fails here rather than silently.
KYIV_OBLAST, KYIV_CITY = SPEC_BY_ID["kyiv"].oblasts
(CHERNIHIV_OBLAST,) = SPEC_BY_ID["chernihiv"].oblasts


@dataclass(frozen=True)
class Zone:
    """One paintable area: a raion, or Kyiv city (which has no raion split in
    the alert system — the whole city alerts as one)."""

    id: str
    name_uk: str  # as the provider names it, which is also what the UI shows
    oblast: str
    query: str  # Nominatim search string — used only by the fetch script


ZONES: tuple[Zone, ...] = (
    Zone("kyiv-city", KYIV_CITY, KYIV_CITY, "Київ, Україна"),
    # Київська область — 7 raions.
    Zone("kyiv-obl-boryspilskyi", "Бориспільський район", KYIV_OBLAST,
         "Бориспільський район, Київська область"),
    Zone("kyiv-obl-brovarskyi", "Броварський район", KYIV_OBLAST,
         "Броварський район, Київська область"),
    Zone("kyiv-obl-buchanskyi", "Бучанський район", KYIV_OBLAST,
         "Бучанський район, Київська область"),
    Zone("kyiv-obl-bilotserkivskyi", "Білоцерківський район", KYIV_OBLAST,
         "Білоцерківський район, Київська область"),
    Zone("kyiv-obl-vyshhorodskyi", "Вишгородський район", KYIV_OBLAST,
         "Вишгородський район, Київська область"),
    Zone("kyiv-obl-obukhivskyi", "Обухівський район", KYIV_OBLAST,
         "Обухівський район, Київська область"),
    Zone("kyiv-obl-fastivskyi", "Фастівський район", KYIV_OBLAST,
         "Фастівський район, Київська область"),
    # Чернігівська область — 5 raions.
    Zone("chernihiv-obl-chernihivskyi", "Чернігівський район", CHERNIHIV_OBLAST,
         "Чернігівський район, Чернігівська область"),
    Zone("chernihiv-obl-nizhynskyi", "Ніжинський район", CHERNIHIV_OBLAST,
         "Ніжинський район, Чернігівська область"),
    Zone("chernihiv-obl-pryluckyi", "Прилуцький район", CHERNIHIV_OBLAST,
         "Прилуцький район, Чернігівська область"),
    Zone("chernihiv-obl-koriukivskyi", "Корюківський район", CHERNIHIV_OBLAST,
         "Корюківський район, Чернігівська область"),
    Zone("chernihiv-obl-novhorod-siverskyi", "Новгород-Сіверський район", CHERNIHIV_OBLAST,
         "Новгород-Сіверський район, Чернігівська область"),
)

# Derived from ZONES and NOT from the region registry, on purpose: a region can
# be declared before anyone has written its raion roster, and a registry-derived
# set would then let the provider's entry through only for `parse_skog` to warn
# once per unknown raion, forever. No Zone rows means the oblast stays invisible,
# which is exactly what a not-yet-covered region should look like.
WATCHED_OBLASTS: frozenset[str] = frozenset(z.oblast for z in ZONES)
ZONE_BY_PLACE: dict[tuple[str, str], Zone] = {(z.oblast, z.name_uk): z for z in ZONES}
# `Zone.oblast` is the provider's display string and `Region` is the track pool;
# nothing mapped the two before. Built over every declared region, so a zone
# added for a region that has no tracks yet still resolves.
OBLAST_REGION: dict[str, Region] = {
    oblast: spec.id for spec in REGION_SPECS for oblast in spec.oblasts
}


def region_of(zone: Zone) -> Region:
    """Which region's map a zone paints on."""
    return OBLAST_REGION[zone.oblast]


@dataclass(frozen=True)
class ZoneState:
    """A zone's current siren state as last reported."""

    zone_id: str
    name_uk: str
    oblast: str
    alert: bool
    # When the provider says this state began. None when it says "never" (it
    # sends a 1970 epoch sentinel for a zone whose state it has never seen
    # change) — the UI then shows the state without a duration.
    changed_at: datetime | None


def unknown_state(zone: Zone) -> ZoneState:
    """A zone the provider didn't mention. Treated as clear-but-unknown rather
    than dropped, so the map always draws all thirteen shapes."""
    return ZoneState(zone_id=zone.id, name_uk=zone.name_uk, oblast=zone.oblast,
                     alert=False, changed_at=None)

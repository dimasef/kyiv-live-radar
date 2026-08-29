"""Air-raid alert zones — the raions whose siren state the map paints.

This is a DIFFERENT layer from `Alert` (the official Kyiv city/oblast siren the
radar itself tracks, still fed by Telegram). It is read-only situational
context: an external provider tells us which raions of the covered oblasts
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
(SUMY_OBLAST,) = SPEC_BY_ID["sumy"].oblasts
(KHARKIV_OBLAST,) = SPEC_BY_ID["kharkiv"].oblasts


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
    # Сумська область — 5 raions.
    Zone("sumy-obl-sumskyi", "Сумський район", SUMY_OBLAST,
         "Сумський район, Сумська область"),
    Zone("sumy-obl-konotopskyi", "Конотопський район", SUMY_OBLAST,
         "Конотопський район, Сумська область"),
    Zone("sumy-obl-okhtyrskyi", "Охтирський район", SUMY_OBLAST,
         "Охтирський район, Сумська область"),
    Zone("sumy-obl-romenskyi", "Роменський район", SUMY_OBLAST,
         "Роменський район, Сумська область"),
    Zone("sumy-obl-shostkynskyi", "Шосткинський район", SUMY_OBLAST,
         "Шосткинський район, Сумська область"),
    # Харківська область — 7 raions.
    #
    # The provider lists EIGHT, because it carries both names of the raion
    # renamed in 2024: «Красноградський» and «Берестинський». They are one
    # place, reported as two rows that disagree — on 2026-08-29 19:37 one said
    # alert, the other відбій. The dead one is identifiable and it is not the
    # one the name suggests: «Берестинський» stamps `changed` as the unix epoch
    # (which `_parse_skog_time` already reads as "never observed"), while
    # «Красноградський» had moved forty minutes earlier. So the OLD name is the
    # live row, and it is the one declared here — `name_uk` is a match key
    # first and a label second.
    #
    # If the provider ever switches, «Красноградський» stops arriving and
    # «Берестинський» starts: the zone would go stale and `_note_unknown` logs
    # the newcomer once. That warning is the intended signal — swap the two
    # lines when it appears. (The gazetteer has the opposite convention for the
    # TOWN, where nothing external constrains us: Берестин is the entry and
    # Красноград its alias.)
    Zone("kharkiv-obl-kharkivskyi", "Харківський район", KHARKIV_OBLAST,
         "Харківський район, Харківська область"),
    Zone("kharkiv-obl-chuhuivskyi", "Чугуївський район", KHARKIV_OBLAST,
         "Чугуївський район, Харківська область"),
    Zone("kharkiv-obl-lozivskyi", "Лозівський район", KHARKIV_OBLAST,
         "Лозівський район, Харківська область"),
    Zone("kharkiv-obl-izyumskyi", "Ізюмський район", KHARKIV_OBLAST,
         "Ізюмський район, Харківська область"),
    Zone("kharkiv-obl-kupianskyi", "Куп'янський район", KHARKIV_OBLAST,
         "Куп'янський район, Харківська область"),
    Zone("kharkiv-obl-bohodukhivskyi", "Богодухівський район", KHARKIV_OBLAST,
         "Богодухівський район, Харківська область"),
    Zone("kharkiv-obl-krasnohradskyi", "Красноградський район", KHARKIV_OBLAST,
         "Берестинський район, Харківська область"),
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
    than dropped, so the map always draws every declared shape."""
    return ZoneState(zone_id=zone.id, name_uk=zone.name_uk, oblast=zone.oblast,
                     alert=False, changed_at=None)

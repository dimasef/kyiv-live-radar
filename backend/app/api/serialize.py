"""Shared ORM -> API/WS serialization (used by REST routes and WS broadcaster)."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import cast

from ..config import settings
from ..domain.attack import classify
from ..domain.journal import DayStat
from ..domain.origins import ORIGIN_BY_KEY, bearing_for
from ..domain.staleness import last_event_at, stale_at
from ..models import Alert, Incident, Notice, Threat, ThreatAxis, ThreatEvent
from ..schemas import (
    AlertOut,
    AxisOut,
    FeedEntryOut,
    IncidentOut,
    JournalDayOut,
    NoticeOut,
    ThreatEventOut,
    ThreatOut,
    _as_utc,
)


def journal_out(stat: DayStat) -> JournalDayOut:
    return JournalDayOut(**asdict(stat))


def event_out(ev: ThreatEvent) -> ThreatEventOut:
    out = ThreatEventOut.model_validate(ev)
    if ev.district is not None:
        out.lat = ev.district.lat
        out.lon = ev.district.lon
    if ev.source is not None:
        out.source_name = ev.source.name
    return out


def threat_out(th: Threat) -> ThreatOut:
    out = ThreatOut.model_validate(th)
    out.events = [event_out(ev) for ev in th.events]
    # Freshness is derived, not stored: one rule, shared with the sweeper that
    # will actually do the closing (domain/staleness.py).
    #
    # _as_utc by hand, because these are ASSIGNED rather than validated:
    # ThreatOut's field validators only run inside model_validate, so a naive
    # value set here would serialize without an offset and the frontend would
    # read it as browser-local time (a Kyiv client showed "186 min ago" for a
    # 6-minute-old sighting — exactly the +3 offset).
    out.last_event_at = _utc(last_event_at(th))
    out.stale_at = _utc(
        stale_at(
            th,
            orphan_windows=settings.stale_minutes_orphan,
            tracked_windows=settings.stale_minutes_tracked,
            default_minutes=settings.track_stale_minutes,
        )
    )
    return out


def _utc(value: datetime) -> datetime:
    return cast(datetime, _as_utc(value))


# Derived (not ORM) fields, so the introspection in threat_out_shallow can't
# getattr them off the row.
_DERIVED_THREAT_FIELDS = frozenset({"events", "last_event_at", "stale_at"})


def threat_out_shallow(th: Threat) -> ThreatOut:
    """Threat fields only, events=[] — for contexts where each event already
    carries its own row (the feed) and loading every track's full event list
    would be wasteful (and would require eager-loading th.events, which isn't
    for a plain event query). Introspects ThreatOut.model_fields (excluding
    `_DERIVED_THREAT_FIELDS`) instead of a hand-written field list, so a new
    field on the schema is picked up automatically — a mismatched ORM attribute
    fails loudly (AttributeError) rather than silently serializing as blank.

    `last_event_at`/`stale_at` stay None here: both need `th.events` loaded
    (which this path deliberately avoids — touching the lazy relationship would
    raise MissingGreenlet under async), and a feed row is history anyway. Only
    the live map cares about freshness."""
    fields = {
        name: getattr(th, name)
        for name in ThreatOut.model_fields
        if name not in _DERIVED_THREAT_FIELDS
    }
    return ThreatOut(**fields, events=[])


def feed_entry_out(ev: ThreatEvent) -> FeedEntryOut:
    return FeedEntryOut(event=event_out(ev), threat=threat_out_shallow(ev.threat))


def notice_out(n: Notice) -> NoticeOut:
    out = NoticeOut.model_validate(n)
    if n.source is not None:
        out.source_name = n.source.name
    return out


def _incident_district_ids(inc: Incident, sentinel_district_id: int | None) -> list[int]:
    """Districts this attack was SEEN over. Impact markers are skipped: a
    district that only ever appears because something landed there would
    otherwise leak the strike location this endpoint is supposed to withhold."""
    seen: list[int] = []
    for th in inc.threats:
        if th.kind == "impact":
            continue
        for ev in th.events:
            if ev.district_id != sentinel_district_id and ev.district_id not in seen:
                seen.append(ev.district_id)
    return seen


def alert_out(a: Alert) -> AlertOut:
    return AlertOut.model_validate(a)


def axis_out(a: ThreatAxis) -> AxisOut:
    origin = ORIGIN_BY_KEY.get(a.origin_key) if a.origin_key else None
    return AxisOut(
        id=a.id,
        sector=a.sector,
        bearing_deg=bearing_for(a.origin_key, a.sector),
        origin_key=a.origin_key,
        origin_name=origin.name_uk if origin is not None else None,
        origin_lat=origin.lat if origin is not None else None,
        origin_lon=origin.lon if origin is not None else None,
        target_type=a.target_type,
        status=a.status,
        corroboration_count=a.corroboration_count,
        created_at=a.created_at,
        last_seen_at=a.last_seen_at,
        expires_at=a.expires_at,
    )


def _is_notable(target_type: str, citywide: bool, impact_count: int, track_count: int) -> bool:
    """Whether an incident is worth a prominent banner — a coordinated
    attack, not a single lone drone (adequately shown by its map dot alone).
    Ported from the frontend's former IncidentBanner.tsx::isNotable — this is
    now the single source of truth; the client just reads `notable`."""
    if target_type == "unknown" and not citywide:
        return False
    return (
        target_type == "ballistic"
        or citywide
        or impact_count > 0
        or track_count + impact_count >= 2
    )


def incident_out(inc: Incident, sentinel_district_id: int | None) -> IncidentOut:
    """Requires `inc.threats` (and each threat's `.events`) eagerly loaded —
    see api/routes.py and broadcast.py for the two loading call sites."""
    track_count = impact_count = target_count = 0
    citywide = False
    districts: set[int] = set()
    for th in inc.threats:
        if th.status == "impact":
            impact_count += 1
            continue  # excluded from the published district set, see below
        if th.scope == "city":
            citywide = True
        else:
            track_count += 1
            target_count += th.target_count or 1
        for ev in th.events:
            if ev.district_id != sentinel_district_id:
                districts.add(ev.district_id)

    cls = classify(inc.attack_types, inc.decoy_mentions, inc.has_hypersonic)

    return IncidentOut(
        id=inc.id,
        started_at=inc.started_at,
        ended_at=inc.ended_at,
        ended_reason=inc.ended_reason,
        target_type=inc.target_type,
        status="active" if inc.ended_at is None else "ended",
        track_count=track_count,
        target_count=target_count,
        # Always 0 on the wire. `impact_count` still drives `notable` (a hit is
        # a strong signal the attack deserves a banner) but the NUMBER is never
        # published — "2 влучання" during a raid tells the attacker how they
        # did just as plainly as a map pin would. The journal reports it once
        # the alert is over.
        impact_count=0,
        citywide=citywide,
        district_count=len(districts),
        district_ids=_incident_district_ids(inc, sentinel_district_id),
        classification=cls.label,
        attack_types=inc.attack_types,
        alert_id=inc.alert_id,
        decoy_suspected=cls.decoy_suspected,
        has_hypersonic=cls.has_hypersonic,
        notable=_is_notable(inc.target_type, citywide, impact_count, track_count),
    )

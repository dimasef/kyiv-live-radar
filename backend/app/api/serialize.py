"""Shared ORM -> API/WS serialization (used by REST routes and WS broadcaster)."""

from __future__ import annotations

from ..domain.attack import classify
from ..domain.origins import ORIGIN_BY_KEY, bearing_for
from ..models import Alert, Incident, Notice, Threat, ThreatAxis, ThreatEvent
from ..schemas import (
    AlertOut,
    AxisOut,
    FeedEntryOut,
    IncidentOut,
    NoticeOut,
    ThreatEventOut,
    ThreatOut,
)


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
    return out


def threat_out_shallow(th: Threat) -> ThreatOut:
    """Threat fields only, events=[] — for contexts where each event already
    carries its own row (the feed) and loading every track's full event list
    would be wasteful (and would require eager-loading th.events, which isn't
    for a plain event query). Introspects ThreatOut.model_fields (excluding
    `events`) instead of a hand-written field list, so a new field on the
    schema is picked up automatically — a mismatched ORM attribute fails
    loudly (AttributeError) rather than silently serializing as blank."""
    fields = {name: getattr(th, name) for name in ThreatOut.model_fields if name != "events"}
    return ThreatOut(**fields, events=[])


def feed_entry_out(ev: ThreatEvent) -> FeedEntryOut:
    return FeedEntryOut(event=event_out(ev), threat=threat_out_shallow(ev.threat))


def notice_out(n: Notice) -> NoticeOut:
    out = NoticeOut.model_validate(n)
    if n.source is not None:
        out.source_name = n.source.name
    return out


def _incident_district_ids(inc: Incident, sentinel_district_id: int | None) -> list[int]:
    seen: list[int] = []
    for th in inc.threats:
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
    track_count = impact_count = 0
    citywide = False
    districts: set[int] = set()
    for th in inc.threats:
        if th.status == "impact":
            impact_count += 1
        elif th.scope == "city":
            citywide = True
        else:
            track_count += 1
        for ev in th.events:
            if ev.district_id != sentinel_district_id:
                districts.add(ev.district_id)

    cls = classify(inc.attack_types, inc.decoy_mentions, inc.has_hypersonic)

    return IncidentOut(
        id=inc.id,
        started_at=inc.started_at,
        ended_at=inc.ended_at,
        target_type=inc.target_type,
        status="active" if inc.ended_at is None else "ended",
        track_count=track_count,
        impact_count=impact_count,
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

"""Shared ORM -> API/WS serialization (used by REST routes and WS broadcaster)."""

from __future__ import annotations

from ..domain.attack import classify
from ..models import Alert, Incident, Notice, Threat, ThreatEvent
from ..schemas import AlertOut, FeedEntryOut, IncidentOut, NoticeOut, ThreatEventOut, ThreatOut


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
    for a plain event query)."""
    return ThreatOut(
        id=th.id,
        created_at=th.created_at,
        target_type=th.target_type,
        status=th.status,
        kind=th.kind,
        closed_reason=th.closed_reason,
        scope=th.scope,
        incident_id=th.incident_id,
        target_count=th.target_count,
        closed_at=th.closed_at,
        corroboration_count=th.corroboration_count,
        has_conflict=th.has_conflict,
        confidence=th.confidence,
        events=[],
    )


def feed_entry_out(ev: ThreatEvent) -> FeedEntryOut:
    return FeedEntryOut(event=event_out(ev), threat=threat_out_shallow(ev.threat))


def notice_out(n: Notice) -> NoticeOut:
    out = NoticeOut.model_validate(n)
    if n.source is not None:
        out.source_name = n.source.name
    return out


def alert_out(a: Alert) -> AlertOut:
    return AlertOut.model_validate(a)


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
        classification=cls.label,
        attack_types=inc.attack_types,
        alert_id=inc.alert_id,
        decoy_suspected=cls.decoy_suspected,
        has_hypersonic=cls.has_hypersonic,
        notable=_is_notable(inc.target_type, citywide, impact_count, track_count),
    )

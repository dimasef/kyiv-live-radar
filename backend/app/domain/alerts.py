"""Official air-raid alert lifecycle — deliberately thin. `apply_alert_signal`
is the entire multi-provider abstraction: a future alerts.in.ua/UkraineAlarm
poller just emits the same `AlertSignal` shape and this function doesn't
change; Telegram becomes a fallback provider, not a special case. No
registry/plugin framework (see CLAUDE.md "чого не робити").
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select

from ..config import settings
from ..models import HOME_REGION, Alert, Incident
from ..timeutil import within

log = logging.getLogger("alerts")


@dataclass
class AlertSignal:
    scope: str  # 'city' | 'oblast' | 'raion'
    action: str  # 'start' | 'end'
    when: datetime
    # Whose siren. Defaults to the deployment's primary region so a caller that
    # predates regions still means what it always meant.
    region: str = HOME_REGION
    provider: str = "telegram"
    raw_id: int | None = None
    alert_type: str = "air_raid"
    # Which raion (domain/alert_zones.Zone.id), for a 'raion'-scoped signal from
    # the district provider. NULL for the official channel — see Alert.zone_id.
    zone_id: str | None = None


def dismiss_alert(alert: Alert, when: datetime) -> None:
    """Admin cancel of a false-positive city alert: end it with reason
    'dismissed' so it drops off the banner and out of the journal. Reversible
    via `restore_alert`. Caller commits + broadcasts."""
    alert.ended_at = when
    alert.closed_reason = "dismissed"
    log.info("alert %s dismissed (admin, scope=%s)", alert.id, alert.scope)


def restore_alert(alert: Alert) -> None:
    """Undo `dismiss_alert` — reopen the alert (clears the failsafe/dismissed
    end so the banner comes back)."""
    alert.ended_at = None
    alert.ended_raw_id = None
    alert.closed_reason = None
    log.info("alert %s restored (admin, scope=%s)", alert.id, alert.scope)


async def _find_open(session, scope: str, region: str, zone_id: str | None = None) -> Alert | None:
    """The open alert for ONE region's scope, and — for a district signal — ONE
    raion.

    Region is part of the key, not a filter on top of it: without it an open
    Kyiv siren made every other region's `start` look like a repeat and no-op,
    so a second region could never raise an alert at all while Kyiv's was
    running. `zone_id` is in the key for exactly the same reason one level down:
    seven raions of Київська область alert independently, and without it the
    first one to sound would swallow the other six.

    NULL is matched as a value, not skipped — the official channel's alerts are
    the `zone_id IS NULL` ones, and they must not be found by a raion lookup.
    """
    return await session.scalar(
        select(Alert).where(
            Alert.scope == scope,
            Alert.region == region,
            Alert.zone_id.is_(None) if zone_id is None else Alert.zone_id == zone_id,
            Alert.ended_at.is_(None),
        )
    )


async def apply_alert_signal(session, signal: AlertSignal) -> Alert | None:
    """Apply a start/end signal, idempotently.

    A repeated 'start' while that scope is already open, or an 'end' with
    nothing open, is a no-op (returns None) — this is the whole idempotency
    guarantee multi-provider fusion needs: two providers racing to report the
    same real-world alert, or a channel reposting its own announcement, never
    double-open/close or double-broadcast. Returns the affected Alert on a
    real transition, else None.
    """
    if signal.action == "start":
        if await _find_open(session, signal.scope, signal.region, signal.zone_id) is not None:
            return None
        alert = Alert(
            scope=signal.scope,
            region=signal.region,
            zone_id=signal.zone_id,
            alert_type=signal.alert_type,
            started_at=signal.when,
            provider=signal.provider,
            started_raw_id=signal.raw_id,
        )
        session.add(alert)
        await session.commit()
        log.info("alert %s opened (region=%s, scope=%s, zone=%s)",
                 alert.id, alert.region, alert.scope, alert.zone_id)
        if signal.scope == "city":
            await _adopt_recent_incident(session, alert, signal.when)
        return alert

    existing = await _find_open(session, signal.scope, signal.region, signal.zone_id)
    if existing is None:
        return None
    existing.ended_at = signal.when
    existing.ended_raw_id = signal.raw_id
    existing.closed_reason = "official"
    await session.commit()
    log.info("alert %s closed (region=%s, scope=%s, zone=%s)",
             existing.id, existing.region, existing.scope, existing.zone_id)
    return existing


async def _adopt_recent_incident(session, alert: Alert, when: datetime) -> None:
    """Ballistic exception: adopt the most recent still-open incident with no
    alert linked yet, if it began within `alert_adopt_lookback_minutes` — a
    ballistic attack is often already underway (incidents.py::attach_to_incident
    creates the incident on first sighting) by the time the official siren
    fires, since sub-minute flight time leaves no room for the alert to lead.
    Without this the incident would stay permanently unlinked even though it's
    plainly the same attack this alert is for. One incident adopted per call;
    a genuinely unrelated second unlinked incident within the window (rare) is
    not addressed here."""
    lookback = timedelta(minutes=settings.alert_adopt_lookback_minutes)
    stmt = (
        select(Incident)
        .where(
            Incident.ended_at.is_(None),
            Incident.alert_id.is_(None),
            # Only this region's attack. Adopting across regions would hand a
            # northern incident to Kyiv's siren and, through `alert_id`, into
            # Kyiv's journal.
            Incident.region == alert.region,
        )
        .order_by(Incident.started_at.desc())
    )
    for inc in await session.scalars(stmt):
        if within(inc.started_at, when, lookback):
            inc.alert_id = alert.id
            await session.commit()
            return




async def close_stale_alerts(session, now: datetime, hours: int) -> list[Alert]:
    """Failsafe: an alert open longer than `hours` with no відбій is almost
    certainly a dead Telethon session that ate the відбій, not a real
    day-long siren — force-close it (`closed_reason='failsafe'`) so a stuck
    banner doesn't mislead the operator indefinitely. The caller is expected
    to log this loudly; silent data loss on the alert channel is exactly the
    failure mode this exists to catch (see domain-model-v2.md risk #8).

    Raion alerts are exempt. Their provider is polled every 20 s and reconciled
    against the DB on every tick, so a stuck one is only possible while the
    provider is unreachable — which the layer already reports as `stale`. Closing
    one here would be worse than useless: a >12 h siren is genuinely routine in
    Сумщина, and the reconciler would reopen it on the next tick, churning a new
    row every failsafe cycle.
    """
    stale_gap = timedelta(hours=hours)
    open_alerts = list(await session.scalars(
        select(Alert).where(Alert.ended_at.is_(None), Alert.zone_id.is_(None))
    ))
    closed = [a for a in open_alerts if not within(a.started_at, now, stale_gap)]
    for a in closed:
        a.ended_at = now
        a.closed_reason = "failsafe"
    if closed:
        await session.commit()
    return closed

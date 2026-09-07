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
from typing import Literal

from sqlalchemy import select

from ..config import settings
from ..models import HOME_REGION, Alert, AlertLevel, AlertThreat, Incident
from ..timeutil import naive, within

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
    # How bad, and of what. Defaults say "this provider names no level", which
    # is the truth for every source that predates the 06.09.2026 split.
    level: AlertLevel = "unknown"
    threat: AlertThreat = "unspecified"


@dataclass
class AlertOutcome:
    """What a signal actually did. `kind` is not derivable from the Alert row
    alone: an escalation and a fresh open both hand back an open alert, and only
    the escalation should raise a feed card instead of a whole new siren."""

    alert: Alert
    kind: Literal["opened", "escalated", "closed"]


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


async def apply_alert_signal(session, signal: AlertSignal) -> AlertOutcome | None:
    """Apply a start/end signal, idempotently.

    A repeated 'start' at the SAME level while that scope is already open, or an
    'end' with nothing open, is a no-op (returns None) — this is the whole
    idempotency guarantee multi-provider fusion needs: two providers racing to
    report the same real-world alert, or a channel reposting its own
    announcement, never double-open/close or double-broadcast.

    A repeated 'start' at a DIFFERENT level is an escalation (or a de-escalation)
    of the alert already running, not a second one. The official channel spells
    this out: «Окремий "Відбій" між різними видами загроз не оголошується» — a
    new announcement replaces the previous one, so «Дронова небезпека» turning
    into «Ракетна загроза» is one continuous siren whose level moved. Closing and
    reopening would put two windows in the journal for one alert and reset the
    banner's clock mid-attack.
    """
    if signal.action == "start":
        open_alert = await _find_open(session, signal.scope, signal.region, signal.zone_id)
        if open_alert is not None:
            return await _relevel(session, open_alert, signal)
        alert = Alert(
            scope=signal.scope,
            region=signal.region,
            zone_id=signal.zone_id,
            alert_type=signal.alert_type,
            level=signal.level,
            threat=signal.threat,
            started_at=signal.when,
            provider=signal.provider,
            started_raw_id=signal.raw_id,
        )
        session.add(alert)
        await session.commit()
        log.info("alert %s opened (region=%s, scope=%s, zone=%s, level=%s/%s)",
                 alert.id, alert.region, alert.scope, alert.zone_id,
                 alert.level, alert.threat)
        if signal.scope == "city":
            await _adopt_recent_incident(session, alert, signal.when)
        return AlertOutcome(alert=alert, kind="opened")

    existing = await _find_open(session, signal.scope, signal.region, signal.zone_id)
    if existing is None:
        return None
    if signal.zone_id is None and naive(existing.started_at) > naive(signal.when):
        # An end older than the alert it would close is a REPLAYED one. A
        # reconnect backfill hands back a whole window of the channel's history,
        # so the відбій of a siren that finished two days ago arrives while
        # tonight's is running — and without this it closed tonight's with
        # Friday's timestamp, after which the same backfill re-opened it as a
        # fresh row. Three duplicate alerts in the live DB on 2026-09-07, two of
        # them stamped `ended_at` earlier than their own `started_at`.
        #
        # Raion alerts (`zone_id`) are deliberately exempt. Their provider is
        # polled, never replayed, so a disagreement there is its clock rather
        # than history repeating — and refusing would leave the siren burning on
        # the map with the reconciler retrying every 20 s. A wrong duration is
        # the lesser failure; a stuck siren is the one this layer exists to
        # avoid.
        log.info("ignoring an end older than the alert it would close "
                 "(alert %s started %s, signal %s)",
                 existing.id, existing.started_at, signal.when)
        return None
    existing.ended_at = signal.when
    existing.ended_raw_id = signal.raw_id
    existing.closed_reason = "official"
    await session.commit()
    log.info("alert %s closed (region=%s, scope=%s, zone=%s)",
             existing.id, existing.region, existing.scope, existing.zone_id)
    return AlertOutcome(alert=existing, kind="closed")


async def _relevel(session, alert: Alert, signal: AlertSignal) -> AlertOutcome | None:
    """A 'start' landing on an already-open alert: move its level, or no-op.

    A provider that names no level ('unknown') never overwrites one that does.
    The two cases that produces are both real: the district roster carries a
    raion the level-carrying source has stopped listing, and a non-Kyiv channel
    still posts the undifferentiated announcement. Forgetting a known level over
    either would show a red raion as an unlabelled one for no gain.
    """
    if signal.level == "unknown" or (
        signal.level == alert.level and signal.threat == alert.threat
    ):
        return None
    # An announcement no newer than the level we already hold describes the
    # PAST, whatever it says. A backfill replays the whole window on every
    # reconnect, so the «дронова небезпека» that opened tonight's siren keeps
    # arriving after the «ракетна загроза» that replaced it — and each replay
    # dragged the alert back to жовтий and filed another feed card for the
    # escalation that followed. Same instant counts as stale: that is the
    # message we already acted on.
    if naive(signal.when) <= naive(alert.level_changed_at or alert.started_at):
        return None
    log.info("alert %s re-levelled %s/%s -> %s/%s (region=%s, scope=%s, zone=%s)",
             alert.id, alert.level, alert.threat, signal.level, signal.threat,
             alert.region, alert.scope, alert.zone_id)
    alert.level = signal.level
    alert.threat = signal.threat
    alert.level_changed_at = signal.when
    await session.commit()
    return AlertOutcome(alert=alert, kind="escalated")


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

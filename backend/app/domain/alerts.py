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
from ..models import Alert, Incident

log = logging.getLogger("alerts")


@dataclass
class AlertSignal:
    scope: str  # 'city' | 'oblast'
    action: str  # 'start' | 'end'
    when: datetime
    provider: str = "telegram"
    raw_id: int | None = None
    alert_type: str = "air_raid"


async def _find_open(session, scope: str) -> Alert | None:
    return await session.scalar(
        select(Alert).where(Alert.scope == scope, Alert.ended_at.is_(None))
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
        if await _find_open(session, signal.scope) is not None:
            return None
        alert = Alert(
            scope=signal.scope,
            alert_type=signal.alert_type,
            started_at=signal.when,
            provider=signal.provider,
            started_raw_id=signal.raw_id,
        )
        session.add(alert)
        await session.commit()
        log.info("alert %s opened (scope=%s)", alert.id, alert.scope)
        if signal.scope == "city":
            await _adopt_recent_incident(session, alert, signal.when)
        return alert

    existing = await _find_open(session, signal.scope)
    if existing is None:
        return None
    existing.ended_at = signal.when
    existing.ended_raw_id = signal.raw_id
    existing.closed_reason = "official"
    await session.commit()
    log.info("alert %s closed (scope=%s)", existing.id, existing.scope)
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
        .where(Incident.ended_at.is_(None), Incident.alert_id.is_(None))
        .order_by(Incident.started_at.desc())
    )
    for inc in await session.scalars(stmt):
        if _within(inc.started_at, when, lookback):
            inc.alert_id = alert.id
            await session.commit()
            return


def _within(a: datetime, b: datetime, gap: timedelta) -> bool:
    an = a.replace(tzinfo=None) if a.tzinfo is not None else a
    bn = b.replace(tzinfo=None) if b.tzinfo is not None else b
    return abs((bn - an).total_seconds()) <= gap.total_seconds()


async def close_stale_alerts(session, now: datetime, hours: int) -> list[Alert]:
    """Failsafe: an alert open longer than `hours` with no відбій is almost
    certainly a dead Telethon session that ate the відбій, not a real
    day-long siren — force-close it (`closed_reason='failsafe'`) so a stuck
    banner doesn't mislead the operator indefinitely. The caller is expected
    to log this loudly; silent data loss on the alert channel is exactly the
    failure mode this exists to catch (see domain-model-v2.md risk #8)."""
    stale_gap = timedelta(hours=hours)
    open_alerts = list(await session.scalars(select(Alert).where(Alert.ended_at.is_(None))))
    closed = [a for a in open_alerts if not _within(a.started_at, now, stale_gap)]
    for a in closed:
        a.ended_at = now
        a.closed_reason = "failsafe"
    if closed:
        await session.commit()
    return closed

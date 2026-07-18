"""Background sweep that auto-closes stale tracks.

A target that goes silent without an explicit "destroyed"/"all-clear" must not
linger as an active threat on the map forever. This closes such tracks and
broadcasts the closure so clients clear them.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import func, select

from ..api.ws import manager
from ..config import settings
from ..db import SessionLocal
from ..domain.alerts import close_stale_alerts
from ..domain.axes import close_stale_axes
from ..domain.incidents import close_stale_incidents
from ..domain.tracking import close_stale_tracks
from ..feeds.health import feed_health, get_status
from ..models import Threat, ThreatAxis, utcnow
from ..observability import metrics
from ..schemas import WSMessage
from .broadcast import broadcast_results
from .results import Broadcast

log = logging.getLogger("sweeper")

# Last broadcast feed-health state, so we log/push only on a real transition
# rather than every tick (feed_health() itself is cheap and stateless — this
# is purely to avoid spamming an identical value once a minute).
_last_feed_ok: bool | None = None


async def run_sweeper() -> None:
    global _last_feed_ok
    while True:
        await asyncio.sleep(settings.sweeper_interval_s)
        try:
            async with SessionLocal() as session:
                now = utcnow()
                closed = await close_stale_tracks(
                    session, now, settings.track_stale_minutes,
                    ballistic_minutes=settings.ballistic_stale_minutes,
                )
                if closed:
                    log.info("auto-closed %d stale track(s)", len(closed))
                    await broadcast_results(session, [Broadcast("status", t) for t in closed])
                ended = await close_stale_incidents(session, now, settings.incident_stale_minutes)
                if ended:
                    log.info("auto-ended %d stale incident(s)", len(ended))
                    await broadcast_results(
                        session, [Broadcast("attack", incident=inc) for inc in ended]
                    )
                expired_axes = await close_stale_axes(session, now)
                if expired_axes:
                    log.info("expired %d stale threat axis(es)", len(expired_axes))
                    await broadcast_results(
                        session, [Broadcast("axis", axis=a) for a in expired_axes]
                    )
                failsafe = await close_stale_alerts(session, now, settings.alert_failsafe_hours)
                if failsafe:
                    log.warning(
                        "FAILSAFE: auto-closed %d stale alert(s) open >%dh — dead "
                        "Telethon session? missed відбій? check the alert channel.",
                        len(failsafe), settings.alert_failsafe_hours,
                    )
                    await broadcast_results(session, [Broadcast("alert", alert=a) for a in failsafe])

                # Sample the live gauges once per sweep (open = not yet closed;
                # impacts self-close at creation so they don't inflate the count).
                open_tracks = await session.scalar(
                    select(func.count()).select_from(Threat).where(Threat.closed_at.is_(None))
                )
                open_axes = await session.scalar(
                    select(func.count()).select_from(ThreatAxis).where(ThreatAxis.expires_at.is_(None))
                )
                metrics.observe_open(open_tracks or 0, open_axes or 0)

            # Listener freshness — seconds since the last LIVE message, only when
            # a real Telegram feed exists and has delivered at least one message
            # (last_message_at is set by live traffic only, never the backfill).
            last_message_at = get_status()["last_message_at"]
            if settings.telegram_enabled and last_message_at is not None:
                metrics.observe_listener_lag((now - last_message_at).total_seconds())

            # Feed health — process-state, not DB-backed, so it lives outside
            # the session block above. Log/push only on a transition.
            ok = feed_health(now, settings.feed_silence_warn_minutes)
            if ok is not None and ok != _last_feed_ok:
                _last_feed_ok = ok
                if not ok:
                    log.warning(
                        "FEED HEALTH: no live Telegram messages / disconnected for >%dm — "
                        "session may be dead; check the listener.",
                        settings.feed_silence_warn_minutes,
                    )
                else:
                    log.info("FEED HEALTH: recovered")
                await manager.broadcast(WSMessage(type="health", feed_ok=ok))
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("stale sweep failed")

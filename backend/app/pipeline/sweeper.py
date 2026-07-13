"""Background sweep that auto-closes stale tracks.

A target that goes silent without an explicit "destroyed"/"all-clear" must not
linger as an active threat on the map forever. This closes such tracks and
broadcasts the closure so clients clear them.
"""

from __future__ import annotations

import asyncio
import logging

from ..api.ws import manager
from ..config import settings
from ..db import SessionLocal
from ..domain.alerts import close_stale_alerts
from ..domain.incidents import close_stale_incidents
from ..domain.tracking import close_stale_tracks
from ..feeds.health import feed_health
from ..models import utcnow
from ..schemas import WSMessage
from .broadcast import broadcast_results
from .results import Broadcast

log = logging.getLogger("sweeper")

_INTERVAL_S = 60

# Last broadcast feed-health state, so we log/push only on a real transition
# rather than every tick (feed_health() itself is cheap and stateless — this
# is purely to avoid spamming an identical value once a minute).
_last_feed_ok: bool | None = None


async def run_sweeper() -> None:
    global _last_feed_ok
    while True:
        await asyncio.sleep(_INTERVAL_S)
        try:
            async with SessionLocal() as session:
                now = utcnow()
                closed = await close_stale_tracks(session, now, settings.track_stale_minutes)
                if closed:
                    log.info("auto-closed %d stale track(s)", len(closed))
                    await broadcast_results(session, [Broadcast("status", t) for t in closed])
                ended = await close_stale_incidents(session, now, settings.incident_stale_minutes)
                if ended:
                    log.info("auto-ended %d stale incident(s)", len(ended))
                    await broadcast_results(
                        session, [Broadcast("attack", incident=inc) for inc in ended]
                    )
                failsafe = await close_stale_alerts(session, now, settings.alert_failsafe_hours)
                if failsafe:
                    log.warning(
                        "FAILSAFE: auto-closed %d stale alert(s) open >%dh — dead "
                        "Telethon session? missed відбій? check the alert channel.",
                        len(failsafe), settings.alert_failsafe_hours,
                    )
                    await broadcast_results(session, [Broadcast("alert", alert=a) for a in failsafe])

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

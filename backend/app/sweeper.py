"""Background sweep that auto-closes stale tracks.

A target that goes silent without an explicit "destroyed"/"all-clear" must not
linger as an active threat on the map forever. This closes such tracks and
broadcasts the closure so clients clear them.
"""

from __future__ import annotations

import asyncio
import logging

from .broadcast import broadcast_results
from .config import settings
from .db import SessionLocal
from .ingest import Broadcast
from .models import utcnow
from .tracking import close_stale_tracks

log = logging.getLogger("sweeper")

_INTERVAL_S = 60


async def run_sweeper() -> None:
    while True:
        await asyncio.sleep(_INTERVAL_S)
        try:
            async with SessionLocal() as session:
                closed = await close_stale_tracks(session, utcnow(), settings.track_stale_minutes)
                if closed:
                    log.info("auto-closed %d stale track(s)", len(closed))
                    await broadcast_results(session, [Broadcast("status", t) for t in closed])
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("stale sweep failed")

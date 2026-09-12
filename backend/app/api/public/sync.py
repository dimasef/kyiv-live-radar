"""GET /sync — one request that brings a reconnecting client up to date.

A reconnect used to be a full `hydrate()`: ten requests per client, and after
a deploy every open tab fires them in the same second. Now the client sends the
position of the last frame it saw and gets back one of three things: nothing
(it missed no frame), the exact frames it missed (replayed from the broadcast
history, applied by the same code as live frames), or — when the server is a
new process or the gap outgrew the history — every slice in one body, spliced
from the read cache's already-rendered bytes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import settings
from ...db import get_session
from ...feeds.alert_zones import zones_out
from ...feeds.health import feed_health
from ...models import Region, utcnow
from ...realtime.ws import manager
from ...schemas import AlertZoneOut, SyncOut
from ..read_cache import get_bytes
from . import situation, sources, threats

router = APIRouter()

_ZONES = TypeAdapter(list[AlertZoneOut])
_FEED_LIMIT = Query(60, ge=1, le=250)


@router.get("/sync", response_model=SyncOut)
async def sync(
    epoch: int | None = Query(None),
    seq: int | None = Query(None),
    limit: int = _FEED_LIMIT,
    region: list[Region] | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    # The position is captured BEFORE any slice is rendered: a frame that lands
    # while the snapshot is assembled is then replayed by the next /sync, and
    # replaying a frame the snapshot already contains is harmless.
    at_epoch, at_seq = manager.epoch, manager.seq
    frames = manager.frames_after(epoch, seq) if epoch is not None and seq is not None else None
    head = b'{"epoch":%d,"seq":%d,' % (at_epoch, at_seq)
    if frames is not None:
        status = b'"status":"current"' if not frames else b'"status":"delta"'
        body = head + status + b',"frames":[' + ",".join(frames).encode() + b"],\"snapshot\":null}"
        return _response(body)

    parts = [
        (b"threats", await _slice(threats.THREATS_ACTIVE, threats.render_active_threats, session)),
        (
            b"incidents",
            await _slice(situation.INCIDENTS_ACTIVE, situation.render_active_incidents, session),
        ),
        (
            b"recent_incidents",
            await _slice(
                situation.incidents_key(20),
                lambda s: situation.render_recent_incidents(s, 20),
                session,
            ),
        ),
        (b"axes", await _slice(situation.AXES_ACTIVE, situation.render_active_axes, session)),
        (
            b"alerts",
            await _slice(
                situation.alerts_key(60), lambda s: situation.render_recent_alerts(s, 60), session
            ),
        ),
        (b"zones", _ZONES.dump_json(zones_out())),
        (
            b"events",
            await _slice(
                threats.events_key(limit, region),
                lambda s: threats.render_recent_events(s, limit, region),
                session,
            ),
        ),
        (
            b"notices",
            await _slice(
                situation.notices_key(30),
                lambda s: situation.render_recent_notices(s, 30),
                session,
            ),
        ),
        (b"sources", await _slice(sources.SOURCES, sources.render_sources, session)),
    ]
    now = utcnow()
    feed_ok = (
        feed_health(now, settings.feed_silence_warn_minutes) if settings.telegram_enabled else None
    )
    tail = b'"server_time":"%s","feed_ok":%s}' % (
        now.isoformat().encode(),
        b"null" if feed_ok is None else (b"true" if feed_ok else b"false"),
    )
    snapshot = b",".join(b'"%s":' % name + body for name, body in parts) + b"," + tail
    return _response(head + b'"status":"full","frames":[],"snapshot":{' + snapshot + b"}")


async def _slice(key: str, render, session: AsyncSession) -> bytes:
    body, _ = await get_bytes(key, lambda: render(session))
    return body


def _response(body: bytes) -> Response:
    return Response(content=body, media_type="application/json")

"""The WebSocket broadcast envelope."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator

from .base import _as_utc
from .situation import AlertOut, AxisOut, IncidentOut, NoticeOut
from .threats import ThreatEventOut, ThreatOut
from .zones import AlertZoneOut


class WSMessage(BaseModel):
    """Envelope broadcast over the WebSocket."""

    # 'event'|'status'|'notice'|'alert'|'attack'|'axis'|'zones'|'health'|'online'|'ping'
    # 'ping' carries only `server_time` — a heartbeat frame (see pipeline/keepalive.py).
    # This list is mirrored by the WSMessage union in frontend/src/types.ts, where
    # it IS exhaustive: adding a frame here without adding it there fails the
    # frontend build. ('hello' used to be listed and was never sent by anything.)
    type: str
    threat: ThreatOut | None = None
    event: ThreatEventOut | None = None
    notice: NoticeOut | None = None
    alert: AlertOut | None = None
    incident: IncidentOut | None = None
    axis: AxisOut | None = None
    # 'zones' frame payload: the raions whose siren state just changed (or the
    # whole roster after a provider outage). See feeds/alert_zones.py.
    zones: list[AlertZoneOut] | None = None
    # 'health' frame payload: whether the live Telegram feed looks healthy —
    # see telegram_listener.py::feed_health.
    feed_ok: bool | None = None
    # 'online' frame payload: how many WS clients are currently connected.
    online: int | None = None
    # Sent on every 'ping': the server's clock. The map fades a target out
    # against absolute `stale_at` timestamps, so a device whose own clock is off
    # by minutes (TV browsers are the usual offender) would fade everything at
    # once — or never. The client keeps the offset and ages targets by it.
    server_time: datetime | None = None
    # Stream position, so a client that reconnects can ask GET /sync for
    # exactly the frames it missed instead of re-fetching everything. `epoch`
    # identifies the server process (a restart starts a new stream), `seq` the
    # frame within it. 'ping'/'online' carry the current position without
    # advancing it — they are not part of the replayable stream.
    epoch: int | None = None
    seq: int | None = None

    _tz_server_time = field_validator("server_time", mode="before")(_as_utc)

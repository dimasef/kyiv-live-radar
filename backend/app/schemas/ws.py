"""The WebSocket broadcast envelope."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator

from .base import _as_utc
from .situation import AlertOut, AxisOut, IncidentOut, NoticeOut
from .threats import ThreatEventOut, ThreatOut


class WSMessage(BaseModel):
    """Envelope broadcast over the WebSocket."""

    # 'event'|'status'|'notice'|'alert'|'attack'|'axis'|'health'|'online'|'hello'|'ping'
    # 'ping' carries only `server_time` — a heartbeat frame (see pipeline/keepalive.py).
    type: str
    threat: ThreatOut | None = None
    event: ThreatEventOut | None = None
    notice: NoticeOut | None = None
    alert: AlertOut | None = None
    incident: IncidentOut | None = None
    axis: AxisOut | None = None
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

    _tz_server_time = field_validator("server_time", mode="before")(_as_utc)

"""Web Push subscription + home-zone payloads."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ..regions import Region


class PushKeysIn(BaseModel):
    """The browser PushSubscription's encryption keys."""

    p256dh: str
    auth: str


class BrowserSubscriptionIn(BaseModel):
    """PushSubscription.toJSON() from the browser."""

    endpoint: str
    keys: PushKeysIn


class HomeZoneIn(BaseModel):
    """The home zone this subscription wants guarded (mirrors the client's
    localStorage home — see frontend store/homeSlice.ts)."""

    lat: float
    lon: float
    radius_km: float = 3.0


class PushPrefsIn(BaseModel):
    """Notification preferences (phase 1). Defaults reproduce the pre-0.10
    behavior (warning floor, every type) plus the citywide push on."""

    min_level: Literal["warning", "danger"] = "warning"
    types: list[Literal["ballistic", "missile", "kab", "shahed", "jet_drone", "fpv"]] = [
        "ballistic", "missile", "kab", "shahed", "jet_drone", "fpv",
    ]
    citywide: bool = True


class PushSubscribeIn(BaseModel):
    """POST /push/subscribe body. Upsert by endpoint; re-POSTed on every home
    or prefs change so the server copy never goes stale."""

    subscription: BrowserSubscriptionIn
    home: HomeZoneIn | None = None
    prefs: PushPrefsIn | None = None
    # Which region this DEVICE wants waking for. Omit to let the server derive
    # it from the home point (the normal case); send it to override, which is
    # what "I am in Kharkiv this week" means without moving the home marker.
    region: Region | None = None


class PushUnsubscribeIn(BaseModel):
    endpoint: str


class PushConfigOut(BaseModel):
    """GET /push/config — whether push is configured server-side, and the VAPID
    public key the browser needs for pushManager.subscribe. Fetched at runtime
    so key rotation never requires a frontend rebuild."""

    enabled: bool
    public_key: str | None = None


class PushPrefsOut(BaseModel):
    """GET /push/prefs — the notification preferences from this user's most
    recently updated subscription, so a NEW device can start from the choices
    they already made instead of the defaults.

    The subscription itself stays per-device (a push endpoint belongs to one
    browser); only the preferences are worth carrying over. `prefs` is None when
    the user has never subscribed anywhere."""

    prefs: PushPrefsIn | None = None

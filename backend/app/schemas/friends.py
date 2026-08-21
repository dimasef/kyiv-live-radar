"""Contacts (friends) and the shareable home point."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from .base import _as_utc


class HomePointOut(BaseModel):
    """A friend's shared home coordinates — a map marker only (no radius)."""

    lat: float
    lon: float


class FriendUserBrief(BaseModel):
    """Minimal public identity of another user, for friend lists / requests."""

    id: int
    email: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None


class PublicUserBrief(BaseModel):
    """Someone seen through a CONTACT's contact list — a name and a picture, and
    deliberately nothing else.

    No email above all: the email is the handle you add a person by, so echoing
    a friend-of-a-friend's would turn one accepted contact into a directory of
    addressable strangers. No home and no presence either — those are disclosures
    their owner grants to their own contacts, not transitively to yours."""

    id: int
    display_name: str | None = None
    avatar_url: str | None = None


class FriendOut(FriendUserBrief):
    """An accepted friend. `home` is populated ONLY when that friend has both set
    a home AND turned sharing on — otherwise null (they stay listed, no marker)."""

    home: HomePointOut | None = None
    # Active within settings.presence_online_seconds. Visible to accepted friends
    # unconditionally — unlike `last_seen_at` below.
    online: bool = False
    # NULL unless they opted into sharing presence AND are currently offline; see
    # domain/presence.py::presence_for for why both conditions apply.
    last_seen_at: datetime | None = None

    _tz = field_validator("last_seen_at", mode="before")(_as_utc)


class FriendRequestOut(BaseModel):
    """One pending friend request, from the current user's point of view."""

    id: int
    direction: str  # 'incoming' (they asked me) | 'outgoing' (I asked them)
    user: FriendUserBrief  # the OTHER party
    created_at: datetime

    _tz = field_validator("created_at", mode="before")(_as_utc)


class FriendRequestsOut(BaseModel):
    incoming: list[FriendRequestOut] = []
    outgoing: list[FriendRequestOut] = []


class SendFriendRequestIn(BaseModel):
    """POST /friends/requests — address a friend request by their email."""

    email: EmailStr


class HomeIn(BaseModel):
    """PUT /me/home — store the owner's home so it follows the account.

    Sharing is NOT set here: it's a separate decision with its own endpoint
    (PATCH /me/home/share). Keeping them apart is what lets the home be saved
    for a user who shares nothing — the whole point of moving it onto the
    account."""

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    radius_km: float | None = Field(default=None, gt=0, le=100)


class ShareToggleIn(BaseModel):
    """PATCH /me/home/share — flip sharing without touching coordinates."""

    share: bool


class HomeStyleIn(BaseModel):
    """PATCH /me/home/style — how the owner's own marker looks on their map.

    Same deal as ContactPrefIn below: the shape ids and palette live in the
    frontend (`lib/markerIcons.ts`), so the server only bounds the size. Both
    halves are written on every call — the picker always holds both — and a
    null resets that half to the default marker."""

    icon: str | None = Field(default=None, max_length=32)
    color: str | None = Field(default=None, max_length=32)
    glow: bool | None = None


class MyHomeOut(BaseModel):
    """GET /me/home — the current user's own stored home + share state.

    `radius_km` sits here rather than on `HomePointOut` on purpose: that model
    is also what FRIENDS receive, and the zone radius is the owner's alone. The
    marker style is owner-only for the same reason — friends label the marker
    themselves (see ContactPrefIn)."""

    home: HomePointOut | None = None
    radius_km: float | None = None
    share_home: bool
    home_icon: str | None = None
    home_color: str | None = None
    # NULL means "never chosen" — the client reads that as a lit marker.
    home_glow: bool | None = None


class ContactPrefIn(BaseModel):
    """PUT /me/contact_prefs/{contact_id} — private labelling for one contact.

    The palette and icon set live in the frontend (`lib/contactMarker.ts`);
    validating against a copy here would just guarantee the two drift, so the
    server only bounds the shape."""

    color: str | None = Field(default=None, max_length=32)
    icon: str | None = Field(default=None, max_length=32)
    glow: bool | None = None
    hidden: bool | None = None


class ContactPrefsOut(BaseModel):
    """GET /me/contact_prefs — every stored per-contact preference, keyed by the
    contact's user id as a string (JSON object keys can't be integers)."""

    prefs: dict[str, dict] = {}


class FriendActionOut(BaseModel):
    """Result of a friend-graph mutation. The client re-fetches the lists after,
    so this only needs to say WHAT happened (used to phrase a toast)."""

    status: str  # 'requested'|'accepted'|'already_pending'|'already_friends'|'removed'|'declined'


class PresencePrefIn(BaseModel):
    """PUT /me/presence — opt in/out of showing friends WHEN you were last active."""

    share_presence: bool


class PresencePrefOut(BaseModel):
    share_presence: bool

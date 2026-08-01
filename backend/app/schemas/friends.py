"""Contacts (friends) and the shareable home point."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


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


class FriendRequestOut(BaseModel):
    """One pending friend request, from the current user's point of view."""

    id: int
    direction: str  # 'incoming' (they asked me) | 'outgoing' (I asked them)
    user: FriendUserBrief  # the OTHER party
    created_at: datetime


class FriendRequestsOut(BaseModel):
    incoming: list[FriendRequestOut] = []
    outgoing: list[FriendRequestOut] = []


class SendFriendRequestIn(BaseModel):
    """POST /friends/requests — address a friend request by their email."""

    email: EmailStr


class HomeShareIn(BaseModel):
    """PUT /me/home — set/update home coordinates and the share flag together."""

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    share: bool = True


class ShareToggleIn(BaseModel):
    """PATCH /me/home/share — flip sharing without touching coordinates."""

    share: bool


class MyHomeOut(BaseModel):
    """GET /me/home — the current user's own stored home + share state."""

    home: HomePointOut | None = None
    share_home: bool


class FriendActionOut(BaseModel):
    """Result of a friend-graph mutation. The client re-fetches the lists after,
    so this only needs to say WHAT happened (used to phrase a toast)."""

    status: str  # 'requested'|'accepted'|'already_pending'|'already_friends'|'removed'|'declined'


class PresencePrefIn(BaseModel):
    """PUT /me/presence — opt in/out of showing friends WHEN you were last active."""

    share_presence: bool


class PresencePrefOut(BaseModel):
    share_presence: bool

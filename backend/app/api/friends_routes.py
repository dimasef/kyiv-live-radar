"""Friends (contacts) + shareable home.

A logged-in user can add another registered user as a friend (by email, with
mutual accept), and — if that friend has opted in — see their home as a marker
on the map. All routes require authentication (get_current_user). No router-level
prefix: paths are written in full, matching app/api/routes.py.

Privacy model:
- Friendship alone never reveals a home. A home is returned only when the owner
  set `share_home=True` (a separate toggle) AND has coordinates.
- Lookup is by exact email (the only unique human handle); a 404 on an unknown
  email is an accepted email-enumeration tradeoff, chosen deliberately.
- The online dot IS visible to accepted friends unconditionally; only the
  last-seen timestamp is gated, by `share_presence` (see domain/presence.py).
"""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import get_current_user
from ..config import settings
from ..db import get_session
from ..domain.presence import presence_for
from ..models import Friendship, User, utcnow
from ..pipeline.contact_push import notify_contact_request, notify_request_accepted
from ..schemas import (
    ContactPrefIn,
    ContactPrefsOut,
    FriendActionOut,
    FriendOut,
    FriendRequestOut,
    FriendRequestsOut,
    FriendUserBrief,
    HomeIn,
    HomePointOut,
    HomeStyleIn,
    MyHomeOut,
    PresencePrefIn,
    PresencePrefOut,
    PublicUserBrief,
    SendFriendRequestIn,
    ShareToggleIn,
)
from .deps import are_friends

friends_router = APIRouter(tags=["friends"])


def _brief(u: User) -> FriendUserBrief:
    return FriendUserBrief(
        id=u.id, email=u.email, display_name=u.display_name, avatar_url=u.avatar_url
    )


def _friend_out(u: User) -> FriendOut:
    """A friend + their home and presence, each behind its own opt-in."""
    home = None
    if u.share_home and u.home_lat is not None and u.home_lon is not None:
        home = HomePointOut(lat=u.home_lat, lon=u.home_lon)
    online, last_seen_at = presence_for(
        last_seen_at=u.last_seen_at,
        share_presence=u.share_presence,
        now=utcnow(),
        window=timedelta(seconds=settings.presence_online_seconds),
    )
    return FriendOut(
        id=u.id,
        email=u.email,
        display_name=u.display_name,
        avatar_url=u.avatar_url,
        home=home,
        online=online,
        last_seen_at=last_seen_at,
    )


def _my_home_out(user: User) -> MyHomeOut:
    home = None
    if user.home_lat is not None and user.home_lon is not None:
        home = HomePointOut(lat=user.home_lat, lon=user.home_lon)
    return MyHomeOut(
        home=home,
        radius_km=user.home_radius_km,
        share_home=user.share_home,
        home_icon=user.home_icon,
        home_color=user.home_color,
        home_glow=user.home_glow,
    )


async def _other(session: AsyncSession, edge: Friendship, me_id: int) -> User | None:
    other_id = edge.addressee_id if edge.requester_id == me_id else edge.requester_id
    return await session.get(User, other_id)


@friends_router.get("/friends", response_model=list[FriendOut])
async def list_friends(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    edges = await session.scalars(
        select(Friendship).where(
            Friendship.status == "accepted",
            or_(
                Friendship.requester_id == user.id,
                Friendship.addressee_id == user.id,
            ),
        )
    )
    out: list[FriendOut] = []
    for edge in edges:
        other = await _other(session, edge, user.id)
        if other is not None:
            out.append(_friend_out(other))
    out.sort(key=lambda f: (f.display_name or f.email or "").lower())
    return out


@friends_router.get("/friends/{user_id}/contacts", response_model=list[PublicUserBrief])
async def list_friend_contacts(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Who one of your contacts is connected to — their profile page (/user/<id>).

    Gated to that person's own accepted contacts, and one hop only: it lists who
    they know, it does not let you walk on from there (asking for a stranger's
    contacts 403s, even if a contact of yours knows them). Each entry is a
    PublicUserBrief — see that model for why the email is absent."""
    if user_id != user.id and not await are_friends(session, user.id, user_id):
        raise HTTPException(status_code=403, detail="Контакти доступні лише контактам")

    edges = await session.scalars(
        select(Friendship).where(
            Friendship.status == "accepted",
            or_(
                Friendship.requester_id == user_id,
                Friendship.addressee_id == user_id,
            ),
        )
    )
    out: list[PublicUserBrief] = []
    for edge in edges:
        other = await _other(session, edge, user_id)
        if other is not None:
            out.append(
                PublicUserBrief(
                    id=other.id, display_name=other.display_name, avatar_url=other.avatar_url
                )
            )
    out.sort(key=lambda u: (u.display_name or "").lower())
    return out


@friends_router.get("/friends/requests", response_model=FriendRequestsOut)
async def list_requests(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    edges = await session.scalars(
        select(Friendship).where(
            Friendship.status == "pending",
            or_(
                Friendship.requester_id == user.id,
                Friendship.addressee_id == user.id,
            ),
        )
    )
    incoming: list[FriendRequestOut] = []
    outgoing: list[FriendRequestOut] = []
    for edge in edges:
        other = await _other(session, edge, user.id)
        if other is None:
            continue
        if edge.addressee_id == user.id:
            incoming.append(
                FriendRequestOut(
                    id=edge.id, direction="incoming", user=_brief(other),
                    created_at=edge.created_at,
                )
            )
        else:
            outgoing.append(
                FriendRequestOut(
                    id=edge.id, direction="outgoing", user=_brief(other),
                    created_at=edge.created_at,
                )
            )
    return FriendRequestsOut(incoming=incoming, outgoing=outgoing)


@friends_router.post("/friends/requests", response_model=FriendActionOut)
async def send_request(
    body: SendFriendRequestIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    target = await session.scalar(
        select(User).where(
            func.lower(User.email) == body.email.lower(), User.is_active.is_(True)
        )
    )
    if target is None:
        raise HTTPException(status_code=404, detail="Користувача з таким email не знайдено")
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="Не можна додати себе")

    # Any existing edge between the two, regardless of who initiated it.
    edge = await session.scalar(
        select(Friendship).where(
            or_(
                (Friendship.requester_id == user.id)
                & (Friendship.addressee_id == target.id),
                (Friendship.requester_id == target.id)
                & (Friendship.addressee_id == user.id),
            )
        )
    )
    if edge is not None:
        if edge.status == "accepted":
            return FriendActionOut(status="already_friends")
        # pending
        if edge.requester_id == user.id:
            return FriendActionOut(status="already_pending")
        # They already requested me → accepting closes the loop (auto-accept).
        edge.status = "accepted"
        edge.responded_at = utcnow()
        await session.commit()
        # target is the ORIGINAL requester — tell them it's accepted.
        await notify_request_accepted(session, target.id, user)
        return FriendActionOut(status="accepted")

    session.add(Friendship(requester_id=user.id, addressee_id=target.id, status="pending"))
    await session.commit()
    await notify_contact_request(session, target.id, user)
    return FriendActionOut(status="requested")


@friends_router.post("/friends/requests/{request_id}/accept", response_model=FriendActionOut)
async def accept_request(
    request_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    edge = await session.get(Friendship, request_id)
    # Only the addressee of a still-pending request can accept it.
    if edge is None or edge.status != "pending" or edge.addressee_id != user.id:
        raise HTTPException(status_code=404, detail="Запит не знайдено")
    edge.status = "accepted"
    edge.responded_at = utcnow()
    await session.commit()
    # Tell the original requester their request was accepted.
    await notify_request_accepted(session, edge.requester_id, user)
    return FriendActionOut(status="accepted")


@friends_router.post("/friends/requests/{request_id}/decline", response_model=FriendActionOut)
async def decline_request(
    request_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    edge = await session.get(Friendship, request_id)
    # Addressee declines OR requester cancels — either party on a pending edge.
    if edge is None or edge.status != "pending" or user.id not in (
        edge.requester_id,
        edge.addressee_id,
    ):
        raise HTTPException(status_code=404, detail="Запит не знайдено")
    await session.delete(edge)
    await session.commit()
    return FriendActionOut(status="declined")


@friends_router.delete("/friends/{user_id}", response_model=FriendActionOut)
async def remove_friend(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    edge = await session.scalar(
        select(Friendship).where(
            Friendship.status == "accepted",
            or_(
                (Friendship.requester_id == user.id) & (Friendship.addressee_id == user_id),
                (Friendship.requester_id == user_id) & (Friendship.addressee_id == user.id),
            ),
        )
    )
    if edge is None:
        raise HTTPException(status_code=404, detail="Друга не знайдено")
    await session.delete(edge)
    await session.commit()
    return FriendActionOut(status="removed")


# --- Own home + sharing ----------------------------------------------------
@friends_router.get("/me/home", response_model=MyHomeOut)
async def get_my_home(user: User = Depends(get_current_user)):
    return _my_home_out(user)


@friends_router.put("/me/home", response_model=MyHomeOut)
async def put_my_home(
    body: HomeIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Store the home on the account. Sharing is untouched — every signed-in
    user's home is saved so it follows them to another device, and whether
    friends may see it stays a separate, explicit choice."""
    user.home_lat = body.lat
    user.home_lon = body.lon
    if body.radius_km is not None:
        user.home_radius_km = body.radius_km
    await session.commit()
    return _my_home_out(user)


@friends_router.patch("/me/home/share", response_model=MyHomeOut)
async def patch_home_share(
    body: ShareToggleIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    user.share_home = body.share
    await session.commit()
    return _my_home_out(user)


@friends_router.patch("/me/home/style", response_model=MyHomeOut)
async def patch_home_style(
    body: HomeStyleIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Set how the owner's own marker looks. Both halves are written every time
    (the picker holds both), so a null resets that half to the default. Nothing
    here reaches friends — they label the marker on their own map."""
    user.home_icon = body.icon
    user.home_color = body.color
    user.home_glow = body.glow
    await session.commit()
    return _my_home_out(user)


@friends_router.delete("/me/home", response_model=MyHomeOut)
async def delete_my_home(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    user.home_lat = None
    user.home_lon = None
    user.home_radius_km = None
    user.share_home = False
    # home_icon/home_color survive on purpose: they say how you like your marker
    # drawn, not where you live, and re-placing a home shouldn't cost the choice.
    await session.commit()
    return _my_home_out(user)


@friends_router.get("/me/presence", response_model=PresencePrefOut)
async def get_my_presence(user: User = Depends(get_current_user)):
    return PresencePrefOut(share_presence=user.share_presence)


@friends_router.put("/me/presence", response_model=PresencePrefOut)
async def put_my_presence(
    body: PresencePrefIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Opt in/out of disclosing WHEN you were last active. Turning it off hides
    the timestamp immediately; it does not stop `last_seen_at` being recorded,
    since the online dot is derived from the same field."""
    user.share_presence = body.share_presence
    await session.commit()
    return PresencePrefOut(share_presence=user.share_presence)


# --- Private per-contact labelling -----------------------------------------
# Colour, icon and "hide on my map", stored per contact. Entirely one-sided: the
# contact is never told, and `hidden` doesn't stop them sharing — it only takes
# their marker off THIS user's map. On the account rather than in localStorage
# because re-picking these on every device is exactly the chore an account
# should absorb (see migration 0023).

# A cap so the blob can't grow without bound if ids are written for contacts that
# no longer exist. Far above any plausible contact list.
_MAX_CONTACT_PREFS = 200


@friends_router.get("/me/contact_prefs", response_model=ContactPrefsOut)
async def get_contact_prefs(user: User = Depends(get_current_user)):
    return ContactPrefsOut(prefs=user.contact_prefs or {})


@friends_router.put("/me/contact_prefs/{contact_id}", response_model=ContactPrefsOut)
async def put_contact_pref(
    contact_id: int,
    body: ContactPrefIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Merge one contact's preferences. Fields left unset are kept, so the
    client can flip `hidden` without having to resend the colour it picked
    three sessions ago."""
    prefs = dict(user.contact_prefs or {})
    key = str(contact_id)
    entry = dict(prefs.get(key) or {})
    for field, value in body.model_dump(exclude_none=True).items():
        entry[field] = value
    if not entry:
        prefs.pop(key, None)
    else:
        if key not in prefs and len(prefs) >= _MAX_CONTACT_PREFS:
            raise HTTPException(status_code=400, detail="Забагато збережених контактів")
        prefs[key] = entry
    user.contact_prefs = prefs
    await session.commit()
    return ContactPrefsOut(prefs=prefs)

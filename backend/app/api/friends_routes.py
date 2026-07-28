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
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import get_current_user
from ..db import get_session
from ..models import Friendship, User, utcnow
from ..schemas import (
    FriendActionOut,
    FriendOut,
    FriendRequestOut,
    FriendRequestsOut,
    FriendUserBrief,
    HomePointOut,
    HomeShareIn,
    MyHomeOut,
    SendFriendRequestIn,
    ShareToggleIn,
)

friends_router = APIRouter(tags=["friends"])


def _brief(u: User) -> FriendUserBrief:
    return FriendUserBrief(
        id=u.id, email=u.email, display_name=u.display_name, avatar_url=u.avatar_url
    )


def _friend_out(u: User) -> FriendOut:
    """A friend + their home, but only when they chose to share it."""
    home = None
    if u.share_home and u.home_lat is not None and u.home_lon is not None:
        home = HomePointOut(lat=u.home_lat, lon=u.home_lon)
    return FriendOut(
        id=u.id,
        email=u.email,
        display_name=u.display_name,
        avatar_url=u.avatar_url,
        home=home,
    )


def _my_home_out(user: User) -> MyHomeOut:
    home = None
    if user.home_lat is not None and user.home_lon is not None:
        home = HomePointOut(lat=user.home_lat, lon=user.home_lon)
    return MyHomeOut(home=home, share_home=user.share_home)


async def _other(session: AsyncSession, edge: Friendship, me_id: int) -> Optional[User]:
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
        return FriendActionOut(status="accepted")

    session.add(Friendship(requester_id=user.id, addressee_id=target.id, status="pending"))
    await session.commit()
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
    body: HomeShareIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    user.home_lat = body.lat
    user.home_lon = body.lon
    user.share_home = body.share
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


@friends_router.delete("/me/home", response_model=MyHomeOut)
async def delete_my_home(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    user.home_lat = None
    user.home_lon = None
    user.share_home = False
    await session.commit()
    return _my_home_out(user)

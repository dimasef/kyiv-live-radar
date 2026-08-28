"""Web Push subscription management for danger-near-home notifications."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.deps import get_optional_user
from ...config import settings
from ...db import get_session
from ...domain.home_danger import raion_ids_for_zone
from ...models import (
    PushSubscription,
    User,
)
from ...schemas import (
    PushConfigOut,
    PushPrefsIn,
    PushPrefsOut,
    PushSubscribeIn,
    PushUnsubscribeIn,
)

router = APIRouter()


@router.get("/push/config", response_model=PushConfigOut)
async def push_config():
    """Whether Web Push is configured server-side + the VAPID public key for
    pushManager.subscribe. The frontend hides its notification control when
    enabled=false."""
    if not settings.push_configured:
        return PushConfigOut(enabled=False)
    return PushConfigOut(enabled=True, public_key=settings.vapid_public_key)


@router.get("/push/prefs", response_model=PushPrefsOut)
async def push_prefs(
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_optional_user),
):
    """This user's last-used notification preferences, for seeding a new device.
    Anonymous callers get nothing — there's no account to carry them from."""
    if user is None:
        return PushPrefsOut()
    row = await session.scalar(
        select(PushSubscription)
        .where(PushSubscription.user_id == user.id)
        .order_by(PushSubscription.updated_at.desc())
    )
    if row is None or not row.prefs:
        return PushPrefsOut()
    return PushPrefsOut(prefs=PushPrefsIn(**row.prefs))


@router.post("/push/subscribe")
async def push_subscribe(
    body: PushSubscribeIn,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_optional_user),
):
    """Register (or update — upsert by endpoint) a push subscription with its
    home zone. Re-POSTed on every home change; moving home resets the per-track
    danger bookkeeping so levels computed for the OLD location can't suppress
    fresh pushes for the new one. When the request carries a valid token, the
    subscription is stamped with the owner so a user's devices can be linked."""
    sub = await session.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == body.subscription.endpoint)
    )
    if sub is None:
        sub = PushSubscription(
            endpoint=body.subscription.endpoint,
            p256dh=body.subscription.keys.p256dh,
            auth=body.subscription.keys.auth,
        )
        session.add(sub)
    else:
        sub.p256dh = body.subscription.keys.p256dh
        sub.auth = body.subscription.keys.auth
    if user is not None:
        sub.user_id = user.id
    if body.prefs is not None:
        sub.prefs = body.prefs.model_dump()
    if body.home is not None:
        home_moved = (sub.home_lat, sub.home_lon) != (body.home.lat, body.home.lon)
        sub.home_lat = body.home.lat
        sub.home_lon = body.home.lon
        sub.home_radius_km = body.home.radius_km
        sub.home_district_ids = await raion_ids_for_zone(
            session, body.home.lat, body.home.lon, body.home.radius_km
        )
        if home_moved:
            sub.danger_state = {}
    # The reader's chosen oblast, sent by the client. Deliberately NOT derived
    # from the home point: the two are separate settings — the region says WHICH
    # pool may wake this device, the home point says where inside it the danger
    # distance is measured from — and inferring one from the other is what made
    # travelling break the alert radius. Absent leaves NULL = the home region.
    if body.region is not None:
        sub.region = body.region
    await session.commit()
    return {"ok": True}


@router.delete("/push/subscribe")
async def push_unsubscribe(body: PushUnsubscribeIn, session: AsyncSession = Depends(get_session)):
    """Idempotent: deleting an unknown endpoint is a no-op success."""
    sub = await session.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
    )
    if sub is not None:
        await session.delete(sub)
        await session.commit()
    return {"ok": True}

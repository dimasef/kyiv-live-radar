"""The «Юзери» tab: who has an account, what they may do, and removing them.

The one thing to understand before changing anything here: **`role` is derived,
not stored intent.** `auth/service.resolve_and_set_role` recomputes it from the
env allowlists on every single login, preserving only 'admin_g'. Everything
below follows from that:

* the assignable set is 'user' and 'admin_g', never plain 'admin';
* revoking a role the allowlist grants is refused rather than silently undone
  at the person's next sign-in;
* every response carries `role_source` — WHY the role reads as it does,
  including the stale-admin case (role='admin', source='default') that nothing
  else in the app surfaces.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...auth.deps import require_admin
from ...auth.service import role_source_for
from ...db import get_session
from ...models import (
    ADMIN_ROLES,
    BugReport,
    Friendship,
    ParserCorrection,
    PushSubscription,
    Source,
    ThreatAnalysis,
    ToponymDismissal,
    User,
)
from ...schemas import AdminUserDeleteOut, AdminUserOut, AdminUserRoleIn

router = APIRouter()


def _out(user: User) -> AdminUserOut:
    """Pure and I/O-free — `user.identities` must already be loaded.

    Both the provider list and the role provenance read that one collection, so
    a page of users costs one extra SELECT in total (selectinload), not one per
    row."""
    providers: list[str] = ["password"] if user.password_hash else []
    providers.extend(sorted({i.provider for i in user.identities}))
    return AdminUserOut(
        id=user.id,
        email=user.email,
        email_verified=user.email_verified,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        role=user.role,
        role_source=role_source_for(user, user.identities),
        providers=providers,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        last_seen_at=user.last_seen_at,
    )


@router.get("/admin/users", response_model=list[AdminUserOut])
async def admin_list_users(
    limit: int = Query(500, ge=1, le=2000),
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """Every account, newest first. Unpaginated and unfiltered by design: this
    is a `sources`-sized table, not a `raw_messages`-sized one, and the console
    filters it client-side (a server-side query param would mean one request per
    keystroke). `limit` is only there so an unbounded table can't produce an
    unbounded response.

    Blocked accounts stay in place rather than sorting to the bottom — the
    operator usually opens this right after blocking someone, to confirm it."""
    stmt = (
        select(User)
        .options(selectinload(User.identities))
        .order_by(User.created_at.desc())
        .limit(limit)
    )
    rows = (await session.scalars(stmt)).all()
    return [_out(u) for u in rows]


@router.patch("/admin/users/{user_id}/role", response_model=AdminUserOut)
async def admin_set_user_role(
    user_id: int,
    body: AdminUserRoleIn,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Grant or revoke console access.

    Only 'user' and 'admin_g' are assignable (see models.AssignableRole): plain
    'admin' is derived from the env allowlists on every login, so it cannot be
    granted here in a way that survives.

    Revoking is refused while the env allowlist still names the person — role
    resolution would hand the role straight back at their next sign-in, and a
    control that silently undoes itself is worse than one that says no. The
    entry has to go from ADMIN_EMAILS / ADMIN_TELEGRAM_IDS first."""
    user = await _load(session, user_id)
    if user.id == admin.id:
        # Demoting yourself locks you out of the console with no way back in;
        # promoting yourself is already true. Neither is worth allowing.
        raise HTTPException(status_code=400, detail="cannot change your own role")
    source = role_source_for(user, user.identities)
    if body.role == "user" and source == "allowlist":
        raise HTTPException(
            status_code=400,
            detail="role is granted by the env allowlist — remove the entry there first",
        )
    if user.role != body.role:
        user.role = body.role
        await session.commit()
    return _out(user)


@router.post("/admin/users/{user_id}/block", response_model=AdminUserOut)
async def admin_block_user(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Deactivate an account. `User.is_active` is already enforced everywhere
    that matters — auth/deps (every authenticated request), login and refresh —
    so this needs no enforcement code of its own: the target's current session
    dies on their very next request."""
    return await _set_user_active(session, user_id, active=False, block_by=admin)


@router.post("/admin/users/{user_id}/unblock", response_model=AdminUserOut)
async def admin_unblock_user(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """No guards here — unblocking is the recovery direction."""
    return await _set_user_active(session, user_id, active=True, block_by=None)


@router.delete("/admin/users/{user_id}", response_model=AdminUserDeleteOut)
async def admin_delete_user(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """HARD-delete an account and everything that only exists because of it —
    irreversible, unlike blocking.

    The dependent rows are removed with EXPLICIT statements rather than left to
    the `ondelete` clauses in the schema, because those don't run everywhere:
    SQLite (dev) ignores foreign keys unless PRAGMA foreign_keys is on, while
    Postgres (prod) enforces them. Leaving it to the DDL would mean dev quietly
    keeping orphan friendship rows that prod deletes — and an orphan friendship
    breaks the OTHER person's contact list.

    What survives, deliberately, with its owner set to NULL: bug reports, parser
    corrections, toponym dismissals, push subscriptions and any source they
    added. Those are project history and training data, not personal effects —
    the same call `ondelete=SET NULL` already makes in the schema."""
    user = await _load(session, user_id)
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="cannot delete your own account")
    if user.role in ADMIN_ROLES:
        raise HTTPException(status_code=400, detail="cannot delete an admin account")

    # Identities are the one dependency with an ORM relationship
    # (cascade="all, delete-orphan"), so session.delete below already removes
    # them on every dialect — deleting them here too would just make SQLAlchemy
    # warn that the cascade matched no rows.
    identities = len(user.identities)
    friendships = await _delete_where(
        session,
        Friendship,
        or_(Friendship.requester_id == user_id, Friendship.addressee_id == user_id),
    )
    analyses = await _delete_where(session, ThreatAnalysis, ThreatAnalysis.user_id == user_id)
    orphaned = 0
    for model, column in (
        (BugReport, BugReport.user_id),
        (ParserCorrection, ParserCorrection.created_by_user_id),
        (ToponymDismissal, ToponymDismissal.created_by_user_id),
        (PushSubscription, PushSubscription.user_id),
        (Source, Source.added_by_user_id),
    ):
        result = await session.execute(
            update(model).where(column == user_id).values({column: None})
        )
        orphaned += result.rowcount or 0

    await session.delete(user)
    await session.commit()
    return AdminUserDeleteOut(
        deleted=user_id,
        identities=identities,
        friendships=friendships,
        analyses=analyses,
        orphaned=orphaned,
    )


async def _delete_where(session: AsyncSession, model, condition) -> int:
    result = await session.execute(delete(model).where(condition))
    return result.rowcount or 0


async def _load(session: AsyncSession, user_id: int) -> User:
    """One user with `identities` loaded — every handler here needs them, for
    `providers` and for the role provenance alike."""
    stmt = select(User).options(selectinload(User.identities)).where(User.id == user_id)
    user = await session.scalar(stmt)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return user


async def _set_user_active(
    session: AsyncSession, user_id: int, *, active: bool, block_by: User | None
) -> AdminUserOut:
    """Set `is_active`, mirroring sources._set_source_active.

    `block_by` is the acting admin on the blocking path (active=False) and None
    on unblock — its presence is what selects the guards."""
    user = await _load(session, user_id)
    if block_by is not None:
        # Self first, though it is formally a subset of the admin check below:
        # this is the message the operator will actually hit, and the general
        # one would read like a bug.
        if user.id == block_by.id:
            raise HTTPException(status_code=400, detail="cannot block your own account")
        # is_active is checked BEFORE role everywhere (auth/deps.py), so a
        # blocked admin has no in-app way back — the undo lives in psql. Not
        # worth offering. Revoking a manual 'admin_g' is a DB operation too,
        # same as granting it was.
        if user.role in ADMIN_ROLES:
            raise HTTPException(status_code=400, detail="cannot block an admin account")
    if user.is_active != active:
        user.is_active = active
        await session.commit()
    return _out(user)

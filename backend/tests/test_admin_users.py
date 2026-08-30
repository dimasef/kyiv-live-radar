"""The «Юзери» admin tab (app/api/admin/users.py): who is listed, why their role
says what it says, and blocking an account end to end.

Driven over ASGITransport with the shared-session fixture from
tests/test_bug_reports.py — cases seed through the session and then read back
over HTTP, so both must see the same transaction.
"""
from __future__ import annotations

from itertools import count

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.security import encode_access
from app.auth.service import role_source_for
from app.config import settings
from app.db import Base, get_session
from app.main import app
from app.models import OAuthIdentity, User


@pytest_asyncio.fixture
async def env(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "auth_jwt_secret", "users-test-secret")
    # Empty by default so a stray real allowlist can't make a seeded user an
    # 'allowlist' admin behind the provenance assertions.
    monkeypatch.setattr(settings, "admin_emails", "")
    monkeypatch.setattr(settings, "admin_telegram_ids", "")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'t.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        async def _override():
            yield s

        app.dependency_overrides[get_session] = _override
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, s
        app.dependency_overrides.clear()
    await engine.dispose()


_seq = count(1)


async def _seed(session, *, role: str = "user", **fields) -> User:
    # A counter, not id(fields): CPython reuses freed dict addresses, which
    # collided on the unique email index.
    fields.setdefault("email", f"{role}-{next(_seq)}@x.com")
    fields.setdefault("password_hash", "x")
    user = User(role=role, **fields)
    session.add(user)
    await session.commit()
    return user


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access(user)}"}


def _row(payload: list[dict], user_id: int) -> dict:
    return next(r for r in payload if r["id"] == user_id)


async def test_admin_users_requires_admin(env):
    """Per route, not per router — app/api/admin/__init__.py keeps the gate on
    each endpoint precisely so this stays assertable one by one."""
    c, s = env
    victim = await _seed(s)
    plain = await _seed(s, role="user")
    admin = await _seed(s, role="admin")
    admin_g = await _seed(s, role="admin_g")

    for method, url in (
        ("get", "/admin/users"),
        ("post", f"/admin/users/{victim.id}/block"),
        ("post", f"/admin/users/{victim.id}/unblock"),
    ):
        call = getattr(c, method)
        assert (await call(url)).status_code == 401, url
        assert (await call(url, headers=_headers(plain))).status_code == 403, url
        assert (await call(url, headers=_headers(admin))).status_code == 200, url
        assert (await call(url, headers=_headers(admin_g))).status_code == 200, url

    # The two routes that take a body / delete need their own loop.
    role_url = f"/admin/users/{victim.id}/role"
    body = {"role": "user"}
    assert (await c.patch(role_url, json=body)).status_code == 401
    assert (await c.patch(role_url, json=body, headers=_headers(plain))).status_code == 403
    assert (await c.patch(role_url, json=body, headers=_headers(admin))).status_code == 200

    del_url = f"/admin/users/{victim.id}"
    assert (await c.delete(del_url)).status_code == 401
    assert (await c.delete(del_url, headers=_headers(plain))).status_code == 403
    assert (await c.delete(del_url, headers=_headers(admin_g))).status_code == 200


async def test_list_shape_and_providers(env):
    """`providers` must read exactly as auth_routes._user_out builds it —
    'password' first, then linked SSO sorted — or the operator's view and the
    user's own profile disagree about how they sign in."""
    c, s = env
    admin = await _seed(s, role="admin")
    native = await _seed(s, email="native@x.com")
    linked = await _seed(s, email="linked@x.com", email_verified=True)
    tg_only = await _seed(s, email=None, password_hash=None)
    s.add_all(
        [
            OAuthIdentity(user_id=linked.id, provider="google", provider_user_id="g1"),
            OAuthIdentity(user_id=tg_only.id, provider="telegram", provider_user_id="42"),
        ]
    )
    await s.commit()

    r = await c.get("/admin/users", headers=_headers(admin))
    assert r.status_code == 200
    rows = r.json()

    assert _row(rows, native.id)["providers"] == ["password"]
    assert _row(rows, linked.id)["providers"] == ["password", "google"]
    assert _row(rows, tg_only.id)["providers"] == ["telegram"]

    assert _row(rows, native.id)["email_verified"] is False
    assert _row(rows, linked.id)["email_verified"] is True
    assert _row(rows, tg_only.id)["email"] is None
    assert all(row["is_active"] is True for row in rows)
    # Newest first.
    assert [row["id"] for row in rows] == sorted((row["id"] for row in rows), reverse=True)


async def test_created_at_carries_an_explicit_utc_offset(env):
    """The _as_utc trap: a naive value serializes zone-less and the browser reads
    it as LOCAL time (same family as the freshness-timestamp bug)."""
    c, s = env
    admin = await _seed(s, role="admin")
    rows = (await c.get("/admin/users", headers=_headers(admin))).json()
    stamp = _row(rows, admin.id)["created_at"]
    assert stamp.endswith("Z") or "+" in stamp[10:], stamp


async def test_role_source_provenance(env, monkeypatch):
    c, s = env
    monkeypatch.setattr(settings, "admin_emails", "Boss@X.com")
    monkeypatch.setattr(settings, "admin_telegram_ids", "777")

    admin = await _seed(s, role="admin", email="boss@x.com", email_verified=True)
    by_tg = await _seed(s, role="admin", email=None, password_hash=None)
    s.add(OAuthIdentity(user_id=by_tg.id, provider="telegram", provider_user_id="777"))
    manual = await _seed(s, role="admin_g", email="manual@x.com")
    plain = await _seed(s, role="user", email="plain@x.com")
    # The whole reason the field exists: role says admin, nothing backs it any
    # more, and role resolution will silently demote them on next login.
    stale = await _seed(s, role="admin", email="was-admin@x.com", email_verified=True)
    await s.commit()

    rows = (await c.get("/admin/users", headers=_headers(admin))).json()
    assert _row(rows, admin.id)["role_source"] == "allowlist"
    assert _row(rows, by_tg.id)["role_source"] == "allowlist"
    assert _row(rows, manual.id)["role_source"] == "manual"
    assert _row(rows, plain.id)["role_source"] == "default"
    assert _row(rows, stale.id)["role_source"] == "default"
    assert _row(rows, stale.id)["role"] == "admin"


async def test_unverified_allowlisted_email_is_not_allowlist_backed(env, monkeypatch):
    """role_for only trusts a VERIFIED email, so a self-registered account on an
    allowlisted address must not read as admin-backed."""
    c, s = env
    monkeypatch.setattr(settings, "admin_emails", "boss@x.com")
    admin = await _seed(s, role="admin_g")
    pretender = await _seed(s, role="user", email="boss@x.com", email_verified=False)

    rows = (await c.get("/admin/users", headers=_headers(admin))).json()
    assert _row(rows, pretender.id)["role_source"] == "default"


async def test_block_then_unblock_round_trip(env):
    """Proves the block is enforced with ZERO new enforcement code: is_active is
    already checked in auth/deps on every authenticated request."""
    c, s = env
    admin = await _seed(s, role="admin")
    victim = await _seed(s, role="user", email="victim@x.com")
    victim_headers = _headers(victim)

    assert (await c.get("/auth/me", headers=victim_headers)).status_code == 200

    r = await c.post(f"/admin/users/{victim.id}/block", headers=_headers(admin))
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    rows = (await c.get("/admin/users", headers=_headers(admin))).json()
    assert _row(rows, victim.id)["is_active"] is False
    # Their live session dies on the very next request.
    assert (await c.get("/auth/me", headers=victim_headers)).status_code == 401

    r = await c.post(f"/admin/users/{victim.id}/unblock", headers=_headers(admin))
    assert r.status_code == 200
    assert r.json()["is_active"] is True
    assert (await c.get("/auth/me", headers=victim_headers)).status_code == 200


async def test_cannot_block_yourself(env):
    c, s = env
    admin = await _seed(s, role="admin")
    r = await c.post(f"/admin/users/{admin.id}/block", headers=_headers(admin))
    assert r.status_code == 400
    assert "own account" in r.json()["detail"]
    await s.refresh(admin)
    assert admin.is_active is True


async def test_cannot_block_an_admin(env):
    """A blocked admin has no in-app way back — is_active is checked before role
    everywhere — so the undo would live in psql. Refuse instead."""
    c, s = env
    admin = await _seed(s, role="admin")
    other = await _seed(s, role="admin_g", email="other-admin@x.com")

    r = await c.post(f"/admin/users/{other.id}/block", headers=_headers(admin))
    assert r.status_code == 400
    assert "admin account" in r.json()["detail"]
    await s.refresh(other)
    assert other.is_active is True


async def test_block_unknown_user_404(env):
    c, s = env
    admin = await _seed(s, role="admin")
    r = await c.post("/admin/users/999999/block", headers=_headers(admin))
    assert r.status_code == 404


@pytest.mark.parametrize(
    "role,email,verified,tg,expected",
    [
        ("admin_g", "any@x.com", True, None, "manual"),
        # 'manual' wins even when the allowlist would ALSO back it: admin_g is
        # the role resolution never recomputes, and that is the fact worth
        # showing.
        ("admin_g", "boss@x.com", True, None, "manual"),
        ("admin", "boss@x.com", True, None, "allowlist"),
        ("admin", "boss@x.com", False, None, "default"),
        ("user", None, False, "777", "allowlist"),
        ("user", None, False, "1", "default"),
        ("user", "nobody@x.com", True, None, "default"),
    ],
)
def test_role_source_for_unit(monkeypatch, role, email, verified, tg, expected):
    monkeypatch.setattr(settings, "admin_emails", "boss@x.com")
    monkeypatch.setattr(settings, "admin_telegram_ids", "777")
    user = User(role=role, email=email, email_verified=verified)
    identities = (
        [OAuthIdentity(provider="telegram", provider_user_id=tg)] if tg else []
    )
    assert role_source_for(user, identities) == expected


def test_role_source_ignores_unparsable_telegram_id(monkeypatch):
    """provider_user_id is a string column; a non-numeric one must be skipped,
    not raise, exactly as the login path's _telegram_ids_for does."""
    monkeypatch.setattr(settings, "admin_telegram_ids", "777")
    user = User(role="user", email=None, email_verified=False)
    identities = [OAuthIdentity(provider="telegram", provider_user_id="not-a-number")]
    assert role_source_for(user, identities) == "default"


async def test_grant_and_revoke_admin_g(env):
    """The only durable grant: 'admin_g' is the role role resolution preserves,
    so it survives the next login — plain 'admin' would not."""
    c, s = env
    admin = await _seed(s, role="admin")
    target = await _seed(s, role="user", email="promote@x.com")

    r = await c.patch(
        f"/admin/users/{target.id}/role", json={"role": "admin_g"}, headers=_headers(admin)
    )
    assert r.status_code == 200
    assert r.json()["role"] == "admin_g"
    assert r.json()["role_source"] == "manual"

    # The promoted account really can reach the console now.
    assert (await c.get("/admin/users", headers=_headers(target))).status_code == 200

    r = await c.patch(
        f"/admin/users/{target.id}/role", json={"role": "user"}, headers=_headers(admin)
    )
    assert r.status_code == 200
    assert r.json()["role"] == "user"
    assert (await c.get("/admin/users", headers=_headers(target))).status_code == 403


async def test_plain_admin_is_not_assignable(env):
    """'admin' is derived from the env allowlists, not stored intent — writing it
    would either change nothing or silently revert at the next sign-in, so the
    enum refuses it before the handler runs."""
    c, s = env
    admin = await _seed(s, role="admin")
    target = await _seed(s, role="user", email="nope@x.com")
    r = await c.patch(
        f"/admin/users/{target.id}/role", json={"role": "admin"}, headers=_headers(admin)
    )
    assert r.status_code == 422


async def test_cannot_revoke_a_role_the_allowlist_grants(env, monkeypatch):
    """Role resolution would hand it straight back on the next login. A control
    that silently undoes itself is worse than one that says no."""
    c, s = env
    monkeypatch.setattr(settings, "admin_emails", "boss@x.com")
    admin = await _seed(s, role="admin_g")
    env_admin = await _seed(s, role="admin", email="boss@x.com", email_verified=True)

    r = await c.patch(
        f"/admin/users/{env_admin.id}/role", json={"role": "user"}, headers=_headers(admin)
    )
    assert r.status_code == 400
    assert "allowlist" in r.json()["detail"]
    await s.refresh(env_admin)
    assert env_admin.role == "admin"

    # Freezing it as a manual role IS allowed — that stops the recompute.
    r = await c.patch(
        f"/admin/users/{env_admin.id}/role", json={"role": "admin_g"}, headers=_headers(admin)
    )
    assert r.status_code == 200
    assert r.json()["role_source"] == "manual"


async def test_cannot_change_your_own_role(env):
    c, s = env
    admin = await _seed(s, role="admin_g")
    r = await c.patch(
        f"/admin/users/{admin.id}/role", json={"role": "user"}, headers=_headers(admin)
    )
    assert r.status_code == 400
    assert "your own role" in r.json()["detail"]
    await s.refresh(admin)
    assert admin.role == "admin_g"


async def test_delete_removes_owned_rows_and_disowns_the_rest(env):
    """The cascade runs as explicit statements, not via the DDL: SQLite ignores
    `ondelete` without PRAGMA foreign_keys while Postgres enforces it, so this
    test would pass for the wrong reason if the route trusted the schema."""
    from app.models import BugReport, Friendship, OAuthIdentity, ThreatAnalysis

    c, s = env
    admin = await _seed(s, role="admin")
    doomed = await _seed(s, role="user", email="doomed@x.com")
    friend = await _seed(s, role="user", email="friend@x.com")
    s.add_all(
        [
            OAuthIdentity(user_id=doomed.id, provider="google", provider_user_id="gg"),
            Friendship(requester_id=doomed.id, addressee_id=friend.id, status="accepted"),
            # The reverse direction must go too — an orphan edge breaks the OTHER
            # person's contact list.
            Friendship(requester_id=friend.id, addressee_id=doomed.id, status="pending"),
            ThreatAnalysis(threat_id=1, user_id=doomed.id, kind="target", card_id=1),
            BugReport(user_id=doomed.id, description="щось зламалось"),
        ]
    )
    await s.commit()

    r = await c.delete(f"/admin/users/{doomed.id}", headers=_headers(admin))
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "deleted": doomed.id,
        "identities": 1,
        "friendships": 2,
        "analyses": 1,
        "orphaned": 1,
    }

    rows = (await c.get("/admin/users", headers=_headers(admin))).json()
    assert all(row["id"] != doomed.id for row in rows)
    assert await s.get(User, doomed.id) is None
    # Kept as project history, disowned rather than deleted.
    report = await s.scalar(select(BugReport).where(BugReport.description == "щось зламалось"))
    assert report is not None and report.user_id is None
    # The friend survives untouched.
    assert await s.get(User, friend.id) is not None


async def test_cannot_delete_yourself_or_an_admin(env):
    c, s = env
    admin = await _seed(s, role="admin")
    other = await _seed(s, role="admin_g", email="other@x.com")

    r = await c.delete(f"/admin/users/{admin.id}", headers=_headers(admin))
    assert r.status_code == 400
    assert "own account" in r.json()["detail"]

    r = await c.delete(f"/admin/users/{other.id}", headers=_headers(admin))
    assert r.status_code == 400
    assert "admin account" in r.json()["detail"]

    assert await s.get(User, admin.id) is not None
    assert await s.get(User, other.id) is not None


async def test_delete_unknown_user_404(env):
    c, s = env
    admin = await _seed(s, role="admin")
    assert (await c.delete("/admin/users/999999", headers=_headers(admin))).status_code == 404

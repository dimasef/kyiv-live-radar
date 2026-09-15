"""GET /admin/online — the readers with no account, and the ones with one.

Two halves, deliberately separate: `group_by_device` is pure and gets the edge
cases (tabs collapsing, a socket with no device id, ordering), while the route
is exercised over HTTP with sockets faked into the live manager — there is no
way to open a real websocket through ASGITransport, and the route's own job is
the account join, not the socket handling.
"""
from __future__ import annotations

from datetime import timedelta
from itertools import count

import pytest
import pytest_asyncio

from app.auth.security import encode_access
from app.config import settings
from app.models import User, utcnow
from app.realtime.sessions import (
    ACCOUNT_LINK_TTL,
    DeviceAccounts,
    LiveSession,
    accounts,
    clean_device_id,
    client_ip,
    describe,
    group_by_device,
)
from app.realtime.ws import manager
from app.timeutil import naive


@pytest_asyncio.fixture
async def env(client, session, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "")
    accounts.clear()
    manager._clients.clear()
    yield client, session
    accounts.clear()
    manager._clients.clear()


_seq = count(1)


async def _seed(session, *, role: str = "user", **fields) -> User:
    fields.setdefault("email", f"online-{role}-{next(_seq)}@x.com")
    fields.setdefault("password_hash", "x")
    user = User(role=role, **fields)
    session.add(user)
    await session.commit()
    return user


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access(user)}"}


def _socket(device: str | None, *, minutes_ago: float = 0, agent: str = "Firefox") -> LiveSession:
    return LiveSession(
        device_id=device,
        connected_at=utcnow() - timedelta(minutes=minutes_ago),
        user_agent=agent,
        ip="1.2.3.4",
    )


# --- pure grouping ---------------------------------------------------------


def test_tabs_of_one_device_collapse_into_one_row():
    """The whole point of the device id: two tabs are one reader, not two."""
    rows = group_by_device([_socket("dev-a", minutes_ago=9), _socket("dev-a")], lambda _d: None)
    assert len(rows) == 1
    assert rows[0].tabs == 2
    # `since` is when they ARRIVED, so the older socket wins.
    assert (naive(utcnow()) - rows[0].since).total_seconds() == pytest.approx(9 * 60, abs=5)


def test_sockets_without_a_device_id_are_never_merged():
    """Nothing says they are the same person, and merging would invent one."""
    rows = group_by_device([_socket(None), _socket(None)], lambda _d: None)
    assert len(rows) == 2
    assert all(r.tabs == 1 and r.device_id is None for r in rows)


def test_rows_are_newest_arrival_first():
    rows = group_by_device(
        [_socket("old", minutes_ago=30), _socket("new"), _socket("mid", minutes_ago=5)],
        lambda _d: None,
    )
    assert [r.device_id for r in rows] == ["new", "mid", "old"]


def test_newest_socket_supplies_the_user_agent():
    """A reader who moved from the phone to the desktop reads as where they are
    now, not where they started."""
    rows = group_by_device(
        [_socket("d", minutes_ago=20, agent="Phone"), _socket("d", agent="Desktop")],
        lambda _d: None,
    )
    assert rows[0].user_agent == "Desktop"


def test_device_id_is_bounded_and_trimmed():
    assert clean_device_id("  abc  ") == "abc"
    assert clean_device_id("") is None
    assert clean_device_id("   ") is None
    assert clean_device_id("x" * 65) is None
    assert clean_device_id("x" * 64) == "x" * 64


def test_client_ip_prefers_the_forwarded_original():
    """Behind Railway the peer is the proxy; the reader is the first forwarded
    entry."""
    assert client_ip({"x-forwarded-for": "9.9.9.9, 10.0.0.1"}, "10.0.0.1") == "9.9.9.9"
    assert client_ip({}, "127.0.0.1") == "127.0.0.1"
    assert client_ip(None, None) is None


def test_describe_caps_a_hostile_user_agent():
    s = describe(device_id="d", headers={"user-agent": "u" * 500}, peer="127.0.0.1")
    assert len(s.user_agent) == 200


# --- device -> account links ----------------------------------------------


def test_account_link_expires():
    links = DeviceAccounts()
    now = utcnow()
    links.note("d", 7, now)
    assert links.user_for("d", now) == 7
    assert links.user_for("d", now + ACCOUNT_LINK_TTL + timedelta(seconds=1)) is None


def test_link_is_last_write_wins():
    """A shared device belongs to whoever used it last — the only thing the
    sockets can support."""
    links = DeviceAccounts()
    links.note("d", 1)
    links.note("d", 2)
    assert links.user_for("d") == 2


def test_forget_user_drops_every_device():
    links = DeviceAccounts()
    links.note("phone", 3)
    links.note("laptop", 3)
    links.note("other", 4)
    links.forget_user(3)
    assert links.user_for("phone") is None
    assert links.user_for("laptop") is None
    assert links.user_for("other") == 4


# --- the route -------------------------------------------------------------


async def test_online_requires_admin(env):
    c, s = env
    plain = await _seed(s)
    admin = await _seed(s, role="admin")
    assert (await c.get("/admin/online")).status_code == 401
    assert (await c.get("/admin/online", headers=_headers(plain))).status_code == 403
    assert (await c.get("/admin/online", headers=_headers(admin))).status_code == 200


async def test_anonymous_readers_are_listed(env):
    """The thing `last_seen_at` can never show: someone in the app with no
    account at all."""
    c, s = env
    admin = await _seed(s, role="admin")
    manager._clients[object()] = _socket("anon-device")

    body = (await c.get("/admin/online", headers=_headers(admin))).json()
    assert body["anonymous"] == 1
    assert body["with_account"] == 0
    assert body["devices"][0]["device_id"] == "anon-device"
    assert body["devices"][0]["user_id"] is None


async def test_a_signed_in_device_is_named(env):
    """The socket carries no token — the account comes from that device's own
    authenticated request (auth/deps notes it)."""
    c, s = env
    admin = await _seed(s, role="admin", display_name="Опер")
    manager._clients[object()] = _socket("admins-laptop")

    # An authenticated call carrying the device header is what forges the link.
    await c.get("/admin/users", headers={**_headers(admin), "X-Device-Id": "admins-laptop"})

    body = (await c.get("/admin/online", headers=_headers(admin))).json()
    row = next(d for d in body["devices"] if d["device_id"] == "admins-laptop")
    assert row["user_id"] == admin.id
    assert row["display_name"] == "Опер"
    assert body["with_account"] == 1
    assert body["anonymous"] == 0


async def test_blocking_an_account_stops_naming_its_socket(env):
    """Its socket outlives the token, and a blocked account still showing as
    online would read as the block not having worked."""
    c, s = env
    admin = await _seed(s, role="admin")
    victim = await _seed(s)
    manager._clients[object()] = _socket("victims-phone")
    await c.get("/auth/me", headers={**_headers(victim), "X-Device-Id": "victims-phone"})
    assert accounts.user_for("victims-phone") == victim.id

    await c.post(f"/admin/users/{victim.id}/block", headers=_headers(admin))

    body = (await c.get("/admin/online", headers=_headers(admin))).json()
    row = next(d for d in body["devices"] if d["device_id"] == "victims-phone")
    assert row["user_id"] is None
    assert body["anonymous"] == 1


async def test_total_counts_sockets_while_rows_count_readers(env):
    """Two tabs are one row here but two connections in the headcount every
    client already sees."""
    c, s = env
    admin = await _seed(s, role="admin")
    manager._clients[object()] = _socket("one-device")
    manager._clients[object()] = _socket("one-device")

    body = (await c.get("/admin/online", headers=_headers(admin))).json()
    assert body["total"] == 2
    assert len(body["devices"]) == 1
    assert body["devices"][0]["tabs"] == 2

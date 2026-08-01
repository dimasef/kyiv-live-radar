"""Friends (contacts) + shareable home API (app/api/friends_routes.py), driven
over ASGITransport — mirrors tests/test_auth_api.py."""
from __future__ import annotations

from datetime import timedelta

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db import Base, get_session
from app.main import app
from app.models import User, utcnow
from app.timeutil import naive


@pytest_asyncio.fixture
async def env(tmp_path, monkeypatch):
    """(client, session) — the session is the SAME one the app uses, so a test
    can set up state the API has no endpoint for (e.g. an old last_seen_at)."""
    monkeypatch.setattr(settings, "auth_jwt_secret", "api-test-secret")
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


@pytest_asyncio.fixture
async def client(env):
    return env[0]


async def _register(c: AsyncClient, email: str) -> str:
    """Register a user and return an Authorization header value (bearer)."""
    r = await c.post("/auth/register", json={"email": email, "password": "password123"})
    assert r.status_code == 200, r.text
    return f"Bearer {r.json()['access']}"


def _auth(token: str) -> dict:
    return {"Authorization": token}


async def test_send_accept_and_list(client):
    c = client
    a = await _register(c, "a@x.com")
    b = await _register(c, "b@x.com")

    # A requests B.
    r = await c.post("/friends/requests", json={"email": "b@x.com"}, headers=_auth(a))
    assert r.status_code == 200 and r.json()["status"] == "requested"

    # B sees it as incoming; A sees it as outgoing.
    r = await c.get("/friends/requests", headers=_auth(b))
    assert r.status_code == 200
    incoming = r.json()["incoming"]
    assert len(incoming) == 1 and incoming[0]["user"]["email"] == "a@x.com"
    req_id = incoming[0]["id"]
    assert incoming[0]["direction"] == "incoming"

    r = await c.get("/friends/requests", headers=_auth(a))
    assert len(r.json()["outgoing"]) == 1 and not r.json()["incoming"]

    # B accepts.
    r = await c.post(f"/friends/requests/{req_id}/accept", headers=_auth(b))
    assert r.status_code == 200 and r.json()["status"] == "accepted"

    # Both now list each other as a friend; no pending left.
    for token, other in ((a, "b@x.com"), (b, "a@x.com")):
        r = await c.get("/friends", headers=_auth(token))
        assert r.status_code == 200
        friends = r.json()
        assert len(friends) == 1 and friends[0]["email"] == other
        assert friends[0]["home"] is None  # neither shared a home yet
        r = await c.get("/friends/requests", headers=_auth(token))
        assert not r.json()["incoming"] and not r.json()["outgoing"]


async def test_self_request_rejected(client):
    c = client
    a = await _register(c, "solo@x.com")
    r = await c.post("/friends/requests", json={"email": "solo@x.com"}, headers=_auth(a))
    assert r.status_code == 400


async def test_unknown_email_404(client):
    c = client
    a = await _register(c, "known@x.com")
    r = await c.post("/friends/requests", json={"email": "ghost@x.com"}, headers=_auth(a))
    assert r.status_code == 404


async def test_reverse_pending_auto_accepts(client):
    c = client
    a = await _register(c, "a2@x.com")
    b = await _register(c, "b2@x.com")

    r = await c.post("/friends/requests", json={"email": "b2@x.com"}, headers=_auth(a))
    assert r.json()["status"] == "requested"
    # Duplicate from the same direction is idempotent, not a second row.
    r = await c.post("/friends/requests", json={"email": "b2@x.com"}, headers=_auth(a))
    assert r.json()["status"] == "already_pending"

    # B requesting A back closes the loop → accepted, no accept step needed.
    r = await c.post("/friends/requests", json={"email": "a2@x.com"}, headers=_auth(b))
    assert r.json()["status"] == "accepted"

    r = await c.get("/friends", headers=_auth(a))
    assert len(r.json()) == 1

    # Requesting an already-friend reports it.
    r = await c.post("/friends/requests", json={"email": "b2@x.com"}, headers=_auth(a))
    assert r.json()["status"] == "already_friends"


async def test_home_share_gate(client):
    c = client
    a = await _register(c, "a3@x.com")
    b = await _register(c, "b3@x.com")
    r = await c.post("/friends/requests", json={"email": "b3@x.com"}, headers=_auth(a))
    req_id = (await c.get("/friends/requests", headers=_auth(b))).json()["incoming"][0]["id"]
    await c.post(f"/friends/requests/{req_id}/accept", headers=_auth(b))

    # B sets a home but does NOT share → A still sees no marker.
    r = await c.put("/me/home", json={"lat": 50.45, "lon": 30.52, "share": False}, headers=_auth(b))
    assert r.status_code == 200 and r.json()["share_home"] is False
    r = await c.get("/friends", headers=_auth(a))
    assert r.json()[0]["home"] is None

    # B turns sharing on → A sees the coordinates.
    r = await c.patch("/me/home/share", json={"share": True}, headers=_auth(b))
    assert r.json()["share_home"] is True
    r = await c.get("/friends", headers=_auth(a))
    home = r.json()[0]["home"]
    assert home == {"lat": 50.45, "lon": 30.52}

    # Clearing home hides it again.
    await c.delete("/me/home", headers=_auth(b))
    r = await c.get("/friends", headers=_auth(a))
    assert r.json()[0]["home"] is None


async def test_decline_and_remove(client):
    c = client
    a = await _register(c, "a4@x.com")
    b = await _register(c, "b4@x.com")

    # Decline a request → nobody becomes a friend.
    await c.post("/friends/requests", json={"email": "b4@x.com"}, headers=_auth(a))
    req_id = (await c.get("/friends/requests", headers=_auth(b))).json()["incoming"][0]["id"]
    r = await c.post(f"/friends/requests/{req_id}/decline", headers=_auth(b))
    assert r.status_code == 200 and r.json()["status"] == "declined"
    assert (await c.get("/friends", headers=_auth(a))).json() == []

    # A re-requests, B accepts, then A removes the friendship.
    await c.post("/friends/requests", json={"email": "b4@x.com"}, headers=_auth(a))
    req_id = (await c.get("/friends/requests", headers=_auth(b))).json()["incoming"][0]["id"]
    await c.post(f"/friends/requests/{req_id}/accept", headers=_auth(b))
    b_id = (await c.get("/friends", headers=_auth(a))).json()[0]["id"]

    r = await c.delete(f"/friends/{b_id}", headers=_auth(a))
    assert r.status_code == 200 and r.json()["status"] == "removed"
    assert (await c.get("/friends", headers=_auth(a))).json() == []
    assert (await c.get("/friends", headers=_auth(b))).json() == []


async def test_requires_auth(client):
    c = client
    assert (await c.get("/friends")).status_code == 401
    assert (await c.get("/me/home")).status_code == 401


async def test_contact_requests_push_the_other_party(client, monkeypatch):
    c = client
    # Make push look configured and capture sends instead of hitting a service.
    monkeypatch.setattr(settings, "vapid_public_key", "x")
    monkeypatch.setattr(settings, "vapid_private_key", "y")
    sent: list[tuple[int | None, dict]] = []

    async def fake_send(session, sub, payload, ttl=300):
        sent.append((sub.user_id, payload))

    monkeypatch.setattr("app.pipeline.contact_push.send_push", fake_send)

    a = await _register(c, "pa@x.com")
    b = await _register(c, "pb@x.com")
    # Both register a (dummy) push subscription, stamped with the owner by token.
    for token, ep in ((a, "a"), (b, "b")):
        r = await c.post(
            "/push/subscribe",
            headers=_auth(token),
            json={
                "subscription": {
                    "endpoint": f"https://push.example/{ep}",
                    "keys": {"p256dh": "k", "auth": "s"},
                },
                "home": None,
            },
        )
        assert r.status_code == 200, r.text

    # A requests B → B's subscription gets a contact-invite push.
    sent.clear()
    await c.post("/friends/requests", json={"email": "pb@x.com"}, headers=_auth(a))
    assert len(sent) == 1
    assert sent[0][1]["kind"] == "contact-invite"
    assert "pa@x.com" in sent[0][1]["body"]

    # B accepts → A (the original requester) gets a contact-accepted push.
    req_id = (await c.get("/friends/requests", headers=_auth(b))).json()["incoming"][0]["id"]
    sent.clear()
    await c.post(f"/friends/requests/{req_id}/accept", headers=_auth(b))
    assert len(sent) == 1
    assert sent[0][1]["kind"] == "contact-accepted"


async def _age_out(session, email: str) -> None:
    """Push a user's last_seen_at well outside the online window."""
    u = await session.scalar(select(User).where(User.email == email))
    u.last_seen_at = naive(utcnow()) - timedelta(hours=3)
    await session.commit()


async def _befriend(c: AsyncClient, a: str, b: str, b_email: str) -> None:
    await c.post("/friends/requests", json={"email": b_email}, headers=_auth(a))
    reqs = (await c.get("/friends/requests", headers=_auth(b))).json()
    await c.post(f"/friends/requests/{reqs['incoming'][0]['id']}/accept", headers=_auth(b))


async def test_friend_shows_online_without_any_opt_in(client):
    """The chosen split: being in the app right now is visible to an accepted
    friend; only the last-seen TIMESTAMP needs consent."""
    c = client
    a = await _register(c, "on-a@x.com")
    b = await _register(c, "on-b@x.com")
    await _befriend(c, a, b, "on-b@x.com")

    # B just authenticated (registering + accepting stamped last_seen_at).
    friend = (await c.get("/friends", headers=_auth(a))).json()[0]
    assert friend["online"] is True
    assert friend["last_seen_at"] is None  # never emitted while online


async def test_last_seen_is_disclosed_by_default(env):
    """share_presence defaults ON (operator decision), so an offline friend's
    last-active time is visible without either side doing anything."""
    c, session = env
    a = await _register(c, "seen-a@x.com")
    b = await _register(c, "seen-b@x.com")
    await _befriend(c, a, b, "seen-b@x.com")
    await _age_out(session, "seen-b@x.com")

    friend = (await c.get("/friends", headers=_auth(a))).json()[0]
    assert friend["online"] is False
    assert friend["last_seen_at"] is not None


async def test_opting_out_hides_the_timestamp_but_not_the_online_dot(env):
    c, session = env
    a = await _register(c, "opt-a@x.com")
    b = await _register(c, "opt-b@x.com")
    await _befriend(c, a, b, "opt-b@x.com")

    r = await c.put("/me/presence", json={"share_presence": False}, headers=_auth(b))
    assert r.status_code == 200 and r.json()["share_presence"] is False

    # B's own request above re-stamped them, so they read as online right now —
    # which the opt-out must NOT suppress.
    friend = (await c.get("/friends", headers=_auth(a))).json()[0]
    assert friend["online"] is True
    assert friend["last_seen_at"] is None

    await _age_out(session, "opt-b@x.com")
    friend = (await c.get("/friends", headers=_auth(a))).json()[0]
    assert friend["online"] is False
    assert friend["last_seen_at"] is None  # still withheld once offline


async def test_presence_is_not_disclosed_to_a_non_friend(client):
    c = client
    a = await _register(c, "stranger@x.com")
    await _register(c, "private@x.com")
    assert (await c.get("/friends", headers=_auth(a))).json() == []

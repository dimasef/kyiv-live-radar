"""Friends (contacts) + shareable home API (app/api/friends_routes.py), driven
over ASGITransport — mirrors tests/test_auth_api.py."""
from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db import Base, get_session
from app.main import app


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
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
            yield c
        app.dependency_overrides.clear()
    await engine.dispose()


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

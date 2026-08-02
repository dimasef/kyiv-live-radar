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

    # B sets a home. Storing it never shares it — PUT /me/home doesn't take a
    # share flag at all, so an unshared home is the default state.
    r = await c.put("/me/home", json={"lat": 50.45, "lon": 30.52}, headers=_auth(b))
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


async def test_home_is_stored_for_a_user_who_shares_nothing(client):
    """The point of moving home onto the account: it must survive opening the
    app on another device even for someone with no contacts and no sharing."""
    c = client
    a = await _register(c, "solo@x.com")

    r = await c.put("/me/home", json={"lat": 50.45, "lon": 30.52, "radius_km": 7},
                    headers=_auth(a))
    assert r.status_code == 200
    body = r.json()
    assert body["home"] == {"lat": 50.45, "lon": 30.52}
    assert body["radius_km"] == 7
    assert body["share_home"] is False  # untouched by storing coordinates

    # A fresh client (a second device) reads it back whole.
    assert (await c.get("/me/home", headers=_auth(a))).json() == body

    # Toggling sharing never has to carry coordinates any more.
    r = await c.patch("/me/home/share", json={"share": True}, headers=_auth(a))
    assert r.json()["home"] == {"lat": 50.45, "lon": 30.52}

    # Clearing wipes the radius too, so it can't reappear on the next device.
    r = await c.delete("/me/home", headers=_auth(a))
    assert r.json()["home"] is None and r.json()["radius_km"] is None


async def _accept(c, asker_headers, target_email, target_headers):
    """Run one request/accept round so a test can build a contact graph."""
    await c.post("/friends/requests", json={"email": target_email}, headers=asker_headers)
    reqs = (await c.get("/friends/requests", headers=target_headers)).json()["incoming"]
    await c.post(f"/friends/requests/{reqs[0]['id']}/accept", headers=target_headers)


async def _user_id(session, email: str) -> int:
    return (await session.scalar(select(User).where(User.email == email))).id


async def test_a_contacts_contact_list_is_visible_to_their_contacts_without_emails(env):
    """The contact profile page (/user/<id>) lists who that person knows — but a
    friend-of-a-friend comes back as a name and a picture only. Publishing their
    email would turn one accepted contact into a directory of addressable
    strangers."""
    c, session = env
    a = await _register(c, "viewer@x.com")
    b = await _register(c, "middle@x.com")
    far = await _register(c, "faraway@x.com")

    await _accept(c, _auth(a), "middle@x.com", _auth(b))
    await _accept(c, _auth(b), "faraway@x.com", _auth(far))

    b_id = await _user_id(session, "middle@x.com")
    r = await c.get(f"/friends/{b_id}/contacts", headers=_auth(a))
    assert r.status_code == 200
    listed = r.json()
    # Everyone B knows: the viewer themselves, and the one they don't.
    assert len(listed) == 2
    for entry in listed:
        assert set(entry) == {"id", "display_name", "avatar_url"}


async def test_a_strangers_contact_list_is_refused(env):
    """One hop only: knowing someone who knows a person does not let you walk on
    to that person's own list."""
    c, session = env
    a = await _register(c, "hopper@x.com")
    await _register(c, "stranger@x.com")
    stranger_id = await _user_id(session, "stranger@x.com")

    r = await c.get(f"/friends/{stranger_id}/contacts", headers=_auth(a))
    assert r.status_code == 403


async def test_home_marker_style_survives_a_device_change_and_a_cleared_home(client):
    """The style is why the setting needs an account at all — it has to read back
    on the next device. Clearing the home keeps it: it says how you like the
    marker drawn, not where you live."""
    c = client
    a = await _register(c, "styler@x.com")

    # A brand-new account has chosen nothing; the client reads every NULL as the
    # default marker, halo included.
    fresh = (await c.get("/me/home", headers=_auth(a))).json()
    assert fresh["home_icon"] is None and fresh["home_glow"] is None

    r = await c.patch("/me/home/style",
                      json={"icon": "hata", "color": "#c084fc", "glow": False},
                      headers=_auth(a))
    assert r.status_code == 200
    assert (r.json()["home_icon"], r.json()["home_color"]) == ("hata", "#c084fc")
    assert r.json()["home_glow"] is False

    stored = (await c.get("/me/home", headers=_auth(a))).json()
    assert stored["home_icon"] == "hata" and stored["home_glow"] is False

    await c.put("/me/home", json={"lat": 50.45, "lon": 30.52, "radius_km": 3},
                headers=_auth(a))
    r = await c.delete("/me/home", headers=_auth(a))
    assert r.json()["home"] is None
    assert r.json()["home_icon"] == "hata"

    # An explicit null is how the default marker comes back.
    r = await c.patch("/me/home/style", json={"icon": None, "color": None, "glow": None},
                      headers=_auth(a))
    assert r.json()["home_icon"] is None and r.json()["home_color"] is None
    assert r.json()["home_glow"] is None


async def test_friends_never_learn_the_home_marker_style(client):
    """It is the OWNER's label on their own map — a contact picks their own for
    that same home (contact_prefs), so nothing about it belongs in FriendOut."""
    c = client
    a = await _register(c, "a10@x.com")
    b = await _register(c, "b10@x.com")
    await c.post("/friends/requests", json={"email": "b10@x.com"}, headers=_auth(a))
    req_id = (await c.get("/friends/requests", headers=_auth(b))).json()["incoming"][0]["id"]
    await c.post(f"/friends/requests/{req_id}/accept", headers=_auth(b))
    await c.put("/me/home", json={"lat": 50.5, "lon": 30.6, "radius_km": 4}, headers=_auth(b))
    await c.patch("/me/home/share", json={"share": True}, headers=_auth(b))
    await c.patch("/me/home/style", json={"icon": "castle", "color": "#34d399"},
                  headers=_auth(b))

    friend = (await c.get("/friends", headers=_auth(a))).json()[0]
    assert friend["home"] == {"lat": 50.5, "lon": 30.6}
    assert "home_icon" not in friend and "home_color" not in friend


async def test_friends_never_learn_the_zone_radius(client):
    """A contact gets a marker, not how wide the owner considers 'near home'."""
    c = client
    a = await _register(c, "a9@x.com")
    b = await _register(c, "b9@x.com")
    await c.post("/friends/requests", json={"email": "b9@x.com"}, headers=_auth(a))
    req_id = (await c.get("/friends/requests", headers=_auth(b))).json()["incoming"][0]["id"]
    await c.post(f"/friends/requests/{req_id}/accept", headers=_auth(b))
    await c.put("/me/home", json={"lat": 50.5, "lon": 30.6, "radius_km": 12}, headers=_auth(b))
    await c.patch("/me/home/share", json={"share": True}, headers=_auth(b))

    home = (await c.get("/friends", headers=_auth(a))).json()[0]["home"]
    assert home == {"lat": 50.5, "lon": 30.6}
    assert "radius_km" not in home


async def test_contact_prefs_round_trip_and_merge(client):
    c = client
    a = await _register(c, "styler@x.com")

    assert (await c.get("/me/contact_prefs", headers=_auth(a))).json() == {"prefs": {}}

    r = await c.put("/me/contact_prefs/7", json={"color": "#c084fc", "icon": "star"},
                    headers=_auth(a))
    assert r.json()["prefs"]["7"] == {"color": "#c084fc", "icon": "star"}

    # A later partial write merges instead of replacing — flipping "hide on my
    # map" must not wipe the colour picked three sessions ago.
    r = await c.put("/me/contact_prefs/7", json={"hidden": True}, headers=_auth(a))
    assert r.json()["prefs"]["7"] == {"color": "#c084fc", "icon": "star", "hidden": True}

    assert (await c.get("/me/contact_prefs", headers=_auth(a))).json()["prefs"]["7"]["hidden"]


async def test_contact_prefs_are_private_to_their_owner(client):
    c = client
    a = await _register(c, "a10@x.com")
    b = await _register(c, "b10@x.com")
    await c.put("/me/contact_prefs/99", json={"color": "#fff"}, headers=_auth(a))
    assert (await c.get("/me/contact_prefs", headers=_auth(b))).json() == {"prefs": {}}

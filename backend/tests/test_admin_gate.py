"""Admin gating of /raw_messages + role resolution from the env allowlist."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.auth.security import encode_access
from app.auth.service import resolve_and_set_role, role_for
from app.config import settings
from app.models import MANUAL_ROLES, User


async def _seed(session, *, role: str) -> str:
    user = User(email=f"{role}@x.com", role=role, password_hash="x")
    session.add(user)
    await session.commit()
    return encode_access(user)


async def test_raw_messages_requires_admin(client, session):
    c, s = client, session

    # Anonymous → 401.
    r = await c.get("/raw_messages")
    assert r.status_code == 401

    # Regular user → 403.
    user_tok = await _seed(s, role="user")
    r = await c.get("/raw_messages", headers={"Authorization": f"Bearer {user_tok}"})
    assert r.status_code == 403

    # Admin → 200.
    admin_tok = await _seed(s, role="admin")
    r = await c.get("/raw_messages", headers={"Authorization": f"Bearer {admin_tok}"})
    assert r.status_code == 200

    # admin_g (manual admin variant) → also 200.
    admin_g_tok = await _seed(s, role="admin_g")
    r = await c.get("/raw_messages", headers={"Authorization": f"Bearer {admin_g_tok}"})
    assert r.status_code == 200


async def test_threat_count_requires_admin(client, session):
    """The newest write route, checked the same way — the gate is per-route
    (api/admin/__init__.py), so a new one is a new opportunity to forget it."""
    c, s = client, session
    body = {"target_count": 2}

    r = await c.patch("/admin/threats/1/count", json=body)
    assert r.status_code == 401

    user_tok = await _seed(s, role="user")
    r = await c.patch("/admin/threats/1/count", json=body,
                      headers={"Authorization": f"Bearer {user_tok}"})
    assert r.status_code == 403

    # Past the gate, into the handler: no such track, hence 404 (not 403).
    admin_tok = await _seed(s, role="admin")
    r = await c.patch("/admin/threats/1/count", json=body,
                      headers={"Authorization": f"Bearer {admin_tok}"})
    assert r.status_code == 404


@pytest.mark.parametrize("role", MANUAL_ROLES)
async def test_resolve_preserves_a_manual_role(client, session, role):
    """A role nothing in the env computes must survive resolution, or it can
    only ever be destroyed by the person signing in.

    That is not hypothetical for 'observer': it is the ONLY role that unlocks
    the consequence layer (models.IMPACT_ROLES), it has always been assignable
    from the console (models.AssignableRole), and until 2026-09-08 resolution
    reset it to 'user' on the very next login — so the operator's grant lasted
    exactly one session and the console reported source='default' meanwhile.
    Parametrized over MANUAL_ROLES so a role added there without teaching
    resolution about it fails here."""
    _c, s = client, session
    user = User(email=f"not-allowlisted-{role}@x.com", role=role, password_hash="x")
    s.add(user)
    await s.commit()
    await resolve_and_set_role(s, user)
    assert user.role == role


async def test_resolve_still_recomputes_a_derived_role(client, session):
    """The other half: preserving manual roles must not turn resolution into a
    no-op. A plain user whose email has since been allowlisted becomes admin at
    their next sign-in, which is the whole reason resolution runs."""
    _c, s = client, session
    settings.admin_emails = "promoted@x.com"
    user = User(email="promoted@x.com", role="user", password_hash="x",
                email_verified=True)
    s.add(user)
    await s.commit()
    await resolve_and_set_role(s, user)
    assert user.role == "admin"


def test_role_for_allowlist(monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "Boss@X.com, second@x.com")

    # Verified allowlisted email → admin (case-insensitive).
    assert role_for("boss@x.com") == "admin"
    # Neither → user.
    assert role_for("stranger@x.com") == "user"
    assert role_for(None) == "user"


async def test_raw_filters_bind_as_lists_over_http(client, session):
    """The multi-select filters ride as REPEATED query params
    (`?region=kyiv&region=sumy`). Worth an HTTP-level test rather than only the
    query-builder ones in test_raw_export: a single-valued signature would still
    answer 200 here while silently keeping just the last value."""
    from app.models import RawMessage, Source

    c, s = client, session
    admin = await _seed(s, role="admin")
    headers = {"Authorization": f"Bearer {admin}"}
    kyiv = Source(name="Київ", channel_key="k", role="spotter", region="kyiv")
    sumy = Source(name="Суми", channel_key="s", role="spotter", region="sumy")
    chern = Source(name="Чернігів", channel_key="c", role="spotter", region="chernihiv")
    s.add_all([kyiv, sumy, chern])
    await s.commit()
    for i, src in enumerate((kyiv, sumy, chern)):
        s.add(RawMessage(source_id=src.id, message_id=i + 1, text="Ціль!",
                         event_time=datetime.now(UTC).replace(tzinfo=None)))
    await s.commit()

    r = await c.get("/raw_messages?region=kyiv&region=sumy", headers=headers)
    assert r.status_code == 200
    assert {m["source_name"] for m in r.json()["items"]} == {"Київ", "Суми"}

    r = await c.get(f"/raw_messages?source_id={kyiv.id}&source_id={chern.id}", headers=headers)
    assert {m["source_name"] for m in r.json()["items"]} == {"Київ", "Чернігів"}

    # The two AND: the Kyiv channel is in the source set but not in the region.
    r = await c.get(f"/raw_messages?source_id={kyiv.id}&region=sumy", headers=headers)
    assert r.json()["items"] == []

    # Neither given = no restriction.
    r = await c.get("/raw_messages", headers=headers)
    assert len(r.json()["items"]) == 3

    # And the source list carries the bindings the UI narrows on.
    r = await c.get("/raw_messages/sources", headers=headers)
    assert {row["name"]: row["regions"] for row in r.json()} == {
        "Київ": ["kyiv"], "Суми": ["sumy"], "Чернігів": ["chernihiv"],
    }

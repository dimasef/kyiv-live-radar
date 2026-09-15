"""Gamification card-analysis API (app/api/gamification.py), driven over
ASGITransport — mirrors tests/test_friends.py. The shared test session is also
handed to each test so it can insert Threat rows to analyse."""
from __future__ import annotations

import random
from datetime import UTC

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.domain.cards import (
    CARD_COUNT,
    CARD_RARITY,
    MILESTONE_CARDS,
    draw_card,
    milestones_owned,
)
from app.models import Threat, ThreatAnalysis


def test_draw_card_is_weighted_by_rarity():
    """Every draw is a valid id, and over many draws commons clearly outnumber
    legendaries (weights 6:3:1) — the rarity actually biases the drop."""
    random.seed(1)
    draws = [draw_card() for _ in range(6000)]
    assert all(1 <= c <= CARD_COUNT for c in draws)
    commons = sum(1 for c in draws if CARD_RARITY[c] == "common")
    legendaries = sum(1 for c in draws if CARD_RARITY[c] == "legendary")
    assert commons > legendaries * 2  # huge margin — not flaky


def test_every_card_has_a_rarity():
    """The deck grows by hand on two sides (this table and the frontend
    catalog), and a card added here without a rarity would silently fall back to
    'common' in the draw — a legendary handed out at 83x its odds. The gap is
    invisible until someone notices the drop rates are wrong, so assert the
    table covers the count exactly."""
    assert set(CARD_RARITY) == set(range(1, CARD_COUNT + 1))
    assert set(MILESTONE_CARDS) <= set(CARD_RARITY)


def test_milestone_cards_never_drop():
    """They are earned by volume of analyses, so a draw must never hand one out
    for free — 6000 draws would hit a 1-in-1650 card several times over. They
    still carry an ordinary rarity, which is exactly why this has to be tested:
    nothing about card 33 marks it as undrawable except its absence from the
    draw pool."""
    random.seed(2)
    assert not {draw_card() for _ in range(6000)} & set(MILESTONE_CARDS)


def test_milestones_owned_counts_every_threshold_passed():
    """Not just the newest one: an account that analysed 1008 targets before this
    shipped has earned 10, 100 AND 1000, and collects all three at once."""
    assert milestones_owned(0) == []
    assert milestones_owned(9) == []
    assert milestones_owned(1008) == [33, 34, 35]
    assert milestones_owned(10000) == [33, 34, 35, 36, 37]


@pytest_asyncio.fixture
async def env(client, session):
    return client, session


async def _register(c: AsyncClient, email: str) -> dict:
    r = await c.post("/auth/register", json={"email": email, "password": "password123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access']}"}


async def _new_threat(s, *, target_type="shahed", status="tracking", scope="district", created_at=None) -> int:
    t = Threat(target_type=target_type, status=status, scope=scope, kind="track")
    if created_at is not None:
        t.created_at = created_at
    s.add(t)
    await s.commit()
    return t.id


async def test_track_analysis_awards_card_and_shows_in_collection(env):
    c, s = env
    auth = await _register(c, "a@x.com")
    tid = await _new_threat(s)

    r = await c.post("/analysis", json={"threat_id": tid, "kind": "track"}, headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "track"
    assert 1 <= body["card_id"] <= CARD_COUNT

    r = await c.get("/analysis/collection", headers=auth)
    assert r.status_code == 200
    col = r.json()
    assert col["total_analyses"] == 1
    assert col["card_count"] == CARD_COUNT
    assert len(col["cards"]) == 1 and col["cards"][0]["count"] == 1


async def _seed_analyses(s, uid: int, n: int) -> None:
    """n past analyses for this user, the way an account that predates milestone
    cards looks."""
    for _ in range(n):
        s.add(ThreatAnalysis(threat_id=await _new_threat(s), user_id=uid, kind="track", card_id=1))
    await s.commit()


async def test_milestone_card_is_awarded_on_the_analysis_that_reaches_it(env):
    c, s = env
    auth = await _register(c, "a@x.com")
    uid = (await c.get("/auth/me", headers=auth)).json()["id"]
    need = MILESTONE_CARDS[33]

    # One short of the first milestone: nothing earned yet.
    await _seed_analyses(s, uid, need - 1)
    col = (await c.get("/analysis/collection", headers=auth)).json()
    assert col["total_analyses"] == need - 1
    assert 33 not in [card["card_id"] for card in col["cards"]]

    r = await c.post(
        "/analysis", json={"threat_id": await _new_threat(s), "kind": "track"}, headers=auth
    )
    assert r.status_code == 200, r.text
    assert r.json()["milestones"] == [33]

    col = (await c.get("/analysis/collection", headers=auth)).json()
    # The milestone card is a single owned copy, and it is NOT itself an analysis.
    assert col["total_analyses"] == need
    earned = [card for card in col["cards"] if card["card_id"] == 33]
    assert len(earned) == 1 and earned[0]["count"] == 1

    # Awarded once: the next analysis reveals nothing and adds no second copy.
    r = await c.post(
        "/analysis", json={"threat_id": await _new_threat(s), "kind": "track"}, headers=auth
    )
    assert r.json()["milestones"] == []
    col = (await c.get("/analysis/collection", headers=auth)).json()
    assert [card["count"] for card in col["cards"] if card["card_id"] == 33] == [1]


async def test_backlog_of_milestones_is_handed_over_on_the_next_analysis(env):
    """The catch-up case this feature exists for: an account with 1008 analyses
    from before milestone cards. Nothing appears in its collection on its own —
    the three cards arrive together on the next analysis, so the reveal can show
    them one after another."""
    c, s = env
    auth = await _register(c, "a@x.com")
    uid = (await c.get("/auth/me", headers=auth)).json()["id"]
    await _seed_analyses(s, uid, 1008)

    col = (await c.get("/analysis/collection", headers=auth)).json()
    assert col["total_analyses"] == 1008
    assert not [card for card in col["cards"] if card["card_id"] in MILESTONE_CARDS]

    r = await c.post(
        "/analysis", json={"threat_id": await _new_threat(s), "kind": "track"}, headers=auth
    )
    assert r.status_code == 200, r.text
    assert r.json()["milestones"] == [33, 34, 35]  # ascending, one reveal each

    col = (await c.get("/analysis/collection", headers=auth)).json()
    owned = {card["card_id"]: card["count"] for card in col["cards"]}
    assert {33: 1, 34: 1, 35: 1}.items() <= owned.items()
    assert 36 not in owned  # 5000 is still out of reach


async def test_remains_requires_destroyed(env):
    c, s = env
    auth = await _register(c, "a@x.com")
    tid = await _new_threat(s, status="tracking")

    # Debris analysis is not offered while the target is still flying.
    r = await c.post("/analysis", json={"threat_id": tid, "kind": "remains"}, headers=auth)
    assert r.status_code == 409

    # Once destroyed: remains works, and the live 'track' analysis no longer does.
    t = await s.get(Threat, tid)
    t.status = "destroyed"
    await s.commit()

    r = await c.post("/analysis", json={"threat_id": tid, "kind": "remains"}, headers=auth)
    assert r.status_code == 200, r.text
    r = await c.post("/analysis", json={"threat_id": tid, "kind": "track"}, headers=auth)
    assert r.status_code == 409


async def test_same_kind_claimed_once_globally(env):
    c, s = env
    a = await _register(c, "a@x.com")
    b = await _register(c, "b@x.com")
    tid = await _new_threat(s)

    r = await c.post("/analysis", json={"threat_id": tid, "kind": "track"}, headers=a)
    assert r.status_code == 200
    # Second user loses the race for the same threat+kind.
    r = await c.post("/analysis", json={"threat_id": tid, "kind": "track"}, headers=b)
    assert r.status_code == 409

    # B's collection stays empty — a lost race awards nothing.
    r = await c.get("/analysis/collection", headers=b)
    assert r.json()["total_analyses"] == 0


async def test_state_reflects_claims(env):
    c, s = env
    a = await _register(c, "a@x.com")
    b = await _register(c, "b@x.com")
    tid = await _new_threat(s)
    await c.post("/analysis", json={"threat_id": tid, "kind": "track"}, headers=a)

    r = await c.get(f"/analysis/threat/{tid}", headers=a)
    st = r.json()
    assert st["track_taken"] is True and st["remains_taken"] is False
    assert st["mine_track"] is not None  # A sees the card it won

    r = await c.get(f"/analysis/threat/{tid}", headers=b)
    st = r.json()
    assert st["track_taken"] is True and st["mine_track"] is None  # taken, but not by B


async def test_state_names_the_other_analyst(env):
    """Whoever won the slot is named to everyone else — the claim being taken is
    already public, and who took it is the part worth seeing."""
    c, s = env
    a = await _register(c, "a@x.com")
    b = await _register(c, "b@x.com")
    await c.patch("/auth/me", json={"display_name": "Спостерігач"}, headers=a)
    tid = await _new_threat(s)
    await c.post("/analysis", json={"threat_id": tid, "kind": "track"}, headers=a)

    st = (await c.get(f"/analysis/threat/{tid}", headers=b)).json()
    assert st["track_by"] == "Спостерігач"
    assert st["remains_by"] is None  # nobody took that slot

    # The winner is never named back to themselves — `mine_track` already says it.
    st = (await c.get(f"/analysis/threat/{tid}", headers=a)).json()
    assert st["track_by"] is None


async def test_state_never_leaks_an_email(env):
    """A name is a disclosure the account chose to make; an address is not. An
    analyst with no display name stays unnamed rather than falling back to it."""
    c, s = env
    a = await _register(c, "nameless@x.com")
    b = await _register(c, "b@x.com")
    tid = await _new_threat(s)
    await c.post("/analysis", json={"threat_id": tid, "kind": "track"}, headers=a)

    body = (await c.get(f"/analysis/threat/{tid}", headers=b)).text
    assert "nameless@x.com" not in body
    assert (await c.get(f"/analysis/threat/{tid}", headers=b)).json()["track_by"] is None


@pytest.mark.parametrize("status", ["lost", "impact", "destroyed"])
async def test_off_board_statuses_allow_remains(env, status):
    c, s = env
    auth = await _register(c, "a@x.com")
    tid = await _new_threat(s, status=status)
    r = await c.post("/analysis", json={"threat_id": tid, "kind": "remains"}, headers=auth)
    assert r.status_code == 200, r.text
    # ...and 'track' is not offered for an off-board target.
    r = await c.post("/analysis", json={"threat_id": tid, "kind": "track"}, headers=auth)
    assert r.status_code == 409


async def test_unknown_type_not_eligible(env):
    c, s = env
    auth = await _register(c, "a@x.com")
    tid = await _new_threat(s, target_type="unknown")
    r = await c.post("/analysis", json={"threat_id": tid, "kind": "track"}, headers=auth)
    assert r.status_code == 409


async def test_city_scope_not_eligible(env):
    c, s = env
    auth = await _register(c, "a@x.com")
    tid = await _new_threat(s, scope="city")
    r = await c.post("/analysis", json={"threat_id": tid, "kind": "track"}, headers=auth)
    assert r.status_code == 409


async def test_stale_target_blocked(env):
    from datetime import datetime, timedelta

    c, s = env
    auth = await _register(c, "a@x.com")
    old = datetime.now(UTC) - timedelta(hours=13)
    tid = await _new_threat(s, created_at=old)
    r = await c.post("/analysis", json={"threat_id": tid, "kind": "track"}, headers=auth)
    assert r.status_code == 409


async def test_gamification_pref_persists_and_syncs(env):
    c, s = env
    auth = await _register(c, "a@x.com")
    # Default off.
    r = await c.get("/auth/me", headers=auth)
    assert r.json()["gamification"] is False
    # Enable → persisted → visible to any other session (e.g. another device).
    r = await c.put("/me/gamification", json={"enabled": True}, headers=auth)
    assert r.status_code == 200 and r.json()["enabled"] is True
    r = await c.get("/auth/me", headers=auth)
    assert r.json()["gamification"] is True


async def test_friend_collection_gated(env):
    c, s = env
    a = await _register(c, "a@x.com")
    b = await _register(c, "b@x.com")
    # ids: a=1, b=2 (fresh DB, registration order).
    # Not friends → B can't see A's collection.
    r = await c.get("/collection/1", headers=b)
    assert r.status_code == 403
    # Your own via the id route always works.
    r = await c.get("/collection/2", headers=b)
    assert r.status_code == 200
    # Become friends (A requests, B accepts) → B can now see A's collection.
    await c.post("/friends/requests", json={"email": "b@x.com"}, headers=a)
    reqs = (await c.get("/friends/requests", headers=b)).json()["incoming"]
    await c.post(f"/friends/requests/{reqs[0]['id']}/accept", headers=b)
    r = await c.get("/collection/1", headers=b)
    assert r.status_code == 200 and "cards" in r.json()


async def test_requires_auth(env):
    c, s = env
    tid = await _new_threat(s)
    r = await c.post("/analysis", json={"threat_id": tid, "kind": "track"})
    assert r.status_code == 401


async def test_bad_kind_rejected(env):
    c, s = env
    auth = await _register(c, "a@x.com")
    tid = await _new_threat(s)
    r = await c.post("/analysis", json={"threat_id": tid, "kind": "nope"}, headers=auth)
    # 422, not 400: `kind` is a Literal on AnalyzeIn, so this is caught by
    # request validation rather than by a hand-rolled check in the handler.
    assert r.status_code == 422

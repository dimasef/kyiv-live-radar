"""Admin manual controls (/admin/*): cancel/restore a false-positive
threat/incident/alert, retype a track, and fix/remove a sighting — the parser
override tools. Verifies the write happened AND that a dismissed entity drops
out of the live views (/threats/active, /incidents/active, journal)."""
from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.pipeline.ingest as ingest
from app.auth.security import encode_access
from app.config import settings
from app.db import Base, get_session
from app.main import app
from app.models import (
    Alert,
    District,
    Incident,
    Notice,
    RawMessage,
    Source,
    Threat,
    ThreatEvent,
    User,
    utcnow,
)
from app.parsing.rules import ParseResult
from app.pipeline.ingest.context import _apply_update


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "auth_jwt_secret", "admin-actions-secret")
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


async def _admin_headers(session) -> dict:
    user = User(email="admin@x.com", role="admin", password_hash="x")
    session.add(user)
    await session.commit()
    return {"Authorization": f"Bearer {encode_access(user)}"}


async def _district(session) -> District:
    d = District(name_uk="Тест", name_en="Test", lat=50.45, lon=30.52)
    session.add(d)
    await session.commit()
    return d


async def _threat_with_event(session, district, *, target_type="shahed", incident=None,
                             source_id=None, closed_at=None):
    threat = Threat(target_type=target_type, status="tracking", closed_at=closed_at)
    if incident is not None:
        threat.incident_id = incident.id
    session.add(threat)
    await session.commit()
    ev = ThreatEvent(threat_id=threat.id, district_id=district.id, raw_text="x",
                     source_id=source_id)
    session.add(ev)
    await session.commit()
    return threat, ev


def _sighting(count: int) -> ParseResult:
    """A parsed corroborating sighting stating a group size — the input the
    running max in _apply_update reads."""
    return ParseResult(
        target_type="shahed", status="sighting", is_new_target=False,
        districts=[], confidence=0.8, target_count=count,
    )


async def _active_ids(c, headers) -> set[int]:
    r = await c.get("/threats/active")
    assert r.status_code == 200
    return {t["id"] for t in r.json()}


async def test_dismiss_and_restore_threat(client):
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    threat, _ = await _threat_with_event(s, d)

    assert threat.id in await _active_ids(c, headers)

    r = await c.post(f"/admin/threats/{threat.id}/dismiss", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "dismissed"
    assert threat.id not in await _active_ids(c, headers)

    r = await c.post(f"/admin/threats/{threat.id}/restore", headers=headers)
    assert r.status_code == 200
    assert threat.id in await _active_ids(c, headers)


async def test_dismiss_excludes_threat_from_journal(client):
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    threat, _ = await _threat_with_event(s, d)

    def total_tracks(payload):
        return sum(day["track_count"] for day in payload["days"])

    before = (await c.get("/journal/days")).json()
    assert total_tracks(before) == 1

    await c.post(f"/admin/threats/{threat.id}/dismiss", headers=headers)
    after = (await c.get("/journal/days")).json()
    assert total_tracks(after) == 0


async def test_retype_updates_incident(client):
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    inc = Incident(target_type="shahed", attack_types=["shahed"])
    s.add(inc)
    await s.commit()
    threat, _ = await _threat_with_event(s, d, target_type="shahed", incident=inc)

    r = await c.patch(
        f"/admin/threats/{threat.id}", json={"target_type": "ballistic"}, headers=headers
    )
    assert r.status_code == 200
    assert r.json()["target_type"] == "ballistic"

    refreshed = await s.get(Incident, inc.id)
    await s.refresh(refreshed)
    assert refreshed.target_type == "ballistic"
    assert refreshed.attack_types == ["ballistic"]


async def test_recount_threat_latches_against_the_parser(client):
    """The whole point of the override: the pipeline grows target_count as a
    running max, so a correction that didn't latch would be undone by the next
    spotter restating a bigger group."""
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    threat, _ = await _threat_with_event(s, d)
    threat.target_count = 5
    await s.commit()

    r = await c.patch(
        f"/admin/threats/{threat.id}/count", json={"target_count": 2}, headers=headers
    )
    assert r.status_code == 200
    assert r.json()["target_count"] == 2
    assert r.json()["target_count_locked"] is True

    _apply_update(_sighting(3), threat)
    assert threat.target_count == 2


async def test_recount_null_hands_the_count_back_to_the_sightings(client):
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    threat, ev = await _threat_with_event(s, d)
    ev.event_target_count = 4
    await s.commit()

    await c.patch(
        f"/admin/threats/{threat.id}/count", json={"target_count": 1}, headers=headers
    )
    r = await c.patch(
        f"/admin/threats/{threat.id}/count", json={"target_count": None}, headers=headers
    )
    assert r.status_code == 200
    assert r.json()["target_count"] == 4
    assert r.json()["target_count_locked"] is False

    _apply_update(_sighting(6), threat)
    assert threat.target_count == 6


async def test_recount_rejects_a_nonsense_count(client):
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    threat, _ = await _threat_with_event(s, d)

    assert (
        await c.patch(
            f"/admin/threats/{threat.id}/count", json={"target_count": 0}, headers=headers
        )
    ).status_code == 422
    assert (
        await c.patch(
            "/admin/threats/999999/count", json={"target_count": 2}, headers=headers
        )
    ).status_code == 404


async def test_retype_of_an_open_track_becomes_the_channel_type_context(client):
    """An operator correcting a LIVE track is the strongest type signal there is,
    and it used to stop at the track. 2026-08-23: a retype to jet_drone at
    18:50:12.7 was followed 5.7 s later by a classifier call answering `shahed`,
    which then became the channel context — a machine guess seeded it, the human
    correction did not."""
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    threat, _ = await _threat_with_event(s, d, target_type="unknown", source_id=7)

    r = await c.patch(
        f"/admin/threats/{threat.id}", json={"target_type": "jet_drone"}, headers=headers
    )
    assert r.status_code == 200
    ctx = ingest._recent_type[7]
    assert ctx.target_type == "jet_drone"
    assert not ctx.inferred      # stated by a human, not read off the feed


async def test_retype_of_a_closed_track_leaves_the_live_context_alone(client):
    """Retyping a CLOSED track is a history correction. Injecting its type into
    the live context would be the same poisoning every other rule in
    ingest/context.py exists to prevent."""
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    threat, _ = await _threat_with_event(
        s, d, target_type="unknown", source_id=7, closed_at=utcnow()
    )

    r = await c.patch(
        f"/admin/threats/{threat.id}", json={"target_type": "ballistic"}, headers=headers
    )
    assert r.status_code == 200
    assert 7 not in ingest._recent_type


async def test_retype_rejects_unknown_type(client):
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    threat, _ = await _threat_with_event(s, d)
    r = await c.patch(
        f"/admin/threats/{threat.id}", json={"target_type": "nonsense"}, headers=headers
    )
    assert r.status_code == 422


async def test_dismiss_incident_cancels_member_tracks(client):
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    inc = Incident(target_type="shahed", attack_types=["shahed"])
    s.add(inc)
    await s.commit()
    threat, _ = await _threat_with_event(s, d, incident=inc)

    r = await c.post(f"/admin/incidents/{inc.id}/dismiss", headers=headers)
    assert r.status_code == 200

    # Incident gone from active, member track cancelled + off the map.
    active_inc = (await c.get("/incidents/active")).json()
    assert inc.id not in {i["id"] for i in active_inc}
    assert threat.id not in await _active_ids(c, headers)
    refreshed = await s.get(Threat, threat.id)
    await s.refresh(refreshed)
    assert refreshed.closed_reason == "dismissed"

    # ...and it never hydrates an "Атаку завершено" summary card on reload.
    recent_inc = (await c.get("/incidents/recent")).json()
    assert inc.id not in {i["id"] for i in recent_inc}

    # Restore brings both back.
    r = await c.post(f"/admin/incidents/{inc.id}/restore", headers=headers)
    assert r.status_code == 200
    assert threat.id in await _active_ids(c, headers)


async def test_delete_last_event_dismisses_track(client):
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    threat, ev = await _threat_with_event(s, d)

    r = await c.delete(f"/admin/events/{ev.id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "dismissed"
    assert threat.id not in await _active_ids(c, headers)


async def test_delete_one_of_two_events_keeps_track(client):
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    threat, ev1 = await _threat_with_event(s, d)
    ev2 = ThreatEvent(threat_id=threat.id, district_id=d.id, raw_text="y")
    s.add(ev2)
    await s.commit()

    r = await c.delete(f"/admin/events/{ev1.id}", headers=headers)
    assert r.status_code == 200
    assert threat.id in await _active_ids(c, headers)
    remaining = list(await s.scalars(select(ThreatEvent).where(ThreatEvent.threat_id == threat.id)))
    assert [e.id for e in remaining] == [ev2.id]


async def test_delete_event_recomputes_corroboration(client):
    # The deleted sighting was one of the two independent sources behind the
    # track — its corroboration/confidence must not outlive it (the «Весь фід»
    # chips read exactly these numbers).
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    src_a = Source(channel_key="a", name="A")
    src_b = Source(channel_key="b", name="B")
    s.add_all([src_a, src_b])
    await s.commit()
    threat, ev1 = await _threat_with_event(s, d)
    ev1.source_id = src_a.id
    ev2 = ThreatEvent(threat_id=threat.id, district_id=d.id, raw_text="y", source_id=src_b.id)
    s.add(ev2)
    threat.corroboration_count = 2
    await s.commit()

    r = await c.delete(f"/admin/events/{ev1.id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["corroboration_count"] == 1
    await s.refresh(threat)
    assert threat.corroboration_count == 1


async def test_add_notice_from_raw_message(client):
    c, s = client
    headers = await _admin_headers(s)
    src = Source(channel_key="a", name="A")
    s.add(src)
    await s.commit()
    raw = RawMessage(text="Вночі очікуємо другу хвилю", source_id=src.id, message_id=77)
    s.add(raw)
    await s.commit()

    r = await c.post(
        f"/admin/raw_messages/{raw.id}/notice", json={"kind": "forecast"}, headers=headers
    )
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "forecast"
    # Defaults to the message's own words, and reads as authoritative (not AI).
    assert body["text"] == "Вночі очікуємо другу хвилю"
    assert body["generated_by"] == "rule"

    # The raw row now traces to it, so a second would be invisible from there.
    again = await c.post(
        f"/admin/raw_messages/{raw.id}/notice", json={"kind": "clear"}, headers=headers
    )
    assert again.status_code == 409

    r = await c.delete(f"/admin/notices/{body['id']}", headers=headers)
    assert r.status_code == 204
    assert await s.scalar(select(func.count()).select_from(Notice)) == 0


async def test_add_notice_uses_given_text(client):
    c, s = client
    headers = await _admin_headers(s)
    raw = RawMessage(text="дуже довгий пост із купою деталей")
    s.add(raw)
    await s.commit()

    r = await c.post(
        f"/admin/raw_messages/{raw.id}/notice",
        json={"kind": "status", "text": "Ситуація спокійна"},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["text"] == "Ситуація спокійна"


async def test_move_event_changes_district(client):
    c, s = client
    headers = await _admin_headers(s)
    d1 = await _district(s)
    d2 = District(name_uk="Друга", name_en="Second", lat=50.5, lon=30.6)
    s.add(d2)
    await s.commit()
    threat, ev = await _threat_with_event(s, d1)

    r = await c.patch(f"/admin/events/{ev.id}", json={"district_id": d2.id}, headers=headers)
    assert r.status_code == 200
    refreshed = await s.get(ThreatEvent, ev.id)
    await s.refresh(refreshed)
    assert refreshed.district_id == d2.id


async def test_move_event_hands_the_track_to_the_new_district_s_region(client):
    # Ingest keeps "a track lives in the region of its LATEST sighting"
    # (handlers._hand_over_region). An admin relocating a sighting can break it,
    # leaving the track corroborating and closing in a pool it left — so the
    # move re-derives the region from the new district.
    c, s = client
    headers = await _admin_headers(s)
    kyiv = await _district(s)
    north = District(
        name_uk="Козелець", name_en="Kozelets", lat=50.9, lon=31.1, region="chernihiv"
    )
    s.add(north)
    await s.commit()
    threat, ev = await _threat_with_event(s, kyiv)
    assert threat.region == "kyiv"

    r = await c.patch(f"/admin/events/{ev.id}", json={"district_id": north.id}, headers=headers)
    assert r.status_code == 200
    await s.refresh(threat)
    assert threat.region == "chernihiv"


async def test_move_event_rejects_unknown_district(client):
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    _, ev = await _threat_with_event(s, d)
    r = await c.patch(f"/admin/events/{ev.id}", json={"district_id": 99999}, headers=headers)
    assert r.status_code == 400


async def test_dismiss_and_restore_alert(client):
    c, s = client
    headers = await _admin_headers(s)
    alert = Alert(scope="city")
    s.add(alert)
    await s.commit()

    assert alert.id in {a["id"] for a in (await c.get("/alerts/active")).json()}

    r = await c.post(f"/admin/alerts/{alert.id}/dismiss", headers=headers)
    assert r.status_code == 200
    assert alert.id not in {a["id"] for a in (await c.get("/alerts/active")).json()}

    r = await c.post(f"/admin/alerts/{alert.id}/restore", headers=headers)
    assert r.status_code == 200
    assert alert.id in {a["id"] for a in (await c.get("/alerts/active")).json()}


async def test_dismissed_list(client):
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    threat, _ = await _threat_with_event(s, d)
    await c.post(f"/admin/threats/{threat.id}/dismiss", headers=headers)

    r = await c.get("/admin/dismissed", headers=headers)
    assert r.status_code == 200
    assert threat.id in {t["id"] for t in r.json()["threats"]}


async def test_admin_actions_require_admin(client):
    c, s = client
    d = await _district(s)
    threat, _ = await _threat_with_event(s, d)

    # Anonymous → 401.
    r = await c.post(f"/admin/threats/{threat.id}/dismiss")
    assert r.status_code == 401

    # Regular user → 403.
    user = User(email="u@x.com", role="user", password_hash="x")
    s.add(user)
    await s.commit()
    r = await c.post(
        f"/admin/threats/{threat.id}/dismiss",
        headers={"Authorization": f"Bearer {encode_access(user)}"},
    )
    assert r.status_code == 403


# --- Regrouping a sighting: move it to another track, or split it out --------

async def test_split_moves_a_sighting_onto_a_track_of_its_own(client):
    """Tracking's split/merge mistakes used to be repairable only by DELETING
    the sighting — throwing away a real observation to fix a grouping error."""
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    threat, keep = await _threat_with_event(s, d, target_type="shahed")
    move = ThreatEvent(threat_id=threat.id, district_id=d.id, raw_text="друга",
                       event_target_type="jet_drone")
    s.add(move)
    await s.commit()

    r = await c.patch(f"/admin/events/{move.id}/threat", json={"threat_id": None},
                      headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["source_threat"]["id"] == threat.id
    assert [e["id"] for e in body["source_threat"]["events"]] == [keep.id]
    new_track = body["threat"]
    assert new_track["id"] != threat.id
    assert [e["id"] for e in new_track["events"]] == [move.id]
    # The event's own reading wins on a split — that is the point of splitting.
    assert new_track["target_type"] == "jet_drone"


async def test_a_split_inherits_the_lifecycle_of_the_track_it_left(client):
    """Splitting a track the sweeper closed an hour ago must give a second
    CLOSED track, not a fresh live dot for a target that is long gone."""
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    threat, _keep = await _threat_with_event(s, d, closed_at=utcnow())
    threat.closed_reason = "stale"
    move = ThreatEvent(threat_id=threat.id, district_id=d.id, raw_text="друга")
    s.add(move)
    await s.commit()

    r = await c.patch(f"/admin/events/{move.id}/threat", json={"threat_id": None},
                      headers=headers)
    assert r.status_code == 200
    new_track = r.json()["threat"]
    assert new_track["closed_at"] is not None
    assert new_track["closed_reason"] == "stale"
    assert threat.id not in await _active_ids(c, headers)


async def test_moving_a_sighting_onto_another_track_merges_them(client):
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    keeper, _ = await _threat_with_event(s, d)
    stray, stray_ev = await _threat_with_event(s, d)

    r = await c.patch(f"/admin/events/{stray_ev.id}/threat",
                      json={"threat_id": keeper.id}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["threat"]["id"] == keeper.id
    assert len(body["threat"]["events"]) == 2
    # The emptied track describes nothing any more — off the map.
    assert body["source_threat"]["events"] == []
    assert stray.id not in await _active_ids(c, headers)


async def test_moving_the_only_sighting_of_a_track_does_not_delete_it(client):
    """A regroup must never lose the observation: the sighting survives the move
    even when its old track is emptied and dismissed by it."""
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    keeper, _ = await _threat_with_event(s, d)
    _stray, stray_ev = await _threat_with_event(s, d)

    await c.patch(f"/admin/events/{stray_ev.id}/threat",
                  json={"threat_id": keeper.id}, headers=headers)
    survived = await s.get(ThreatEvent, stray_ev.id)
    await s.refresh(survived)
    assert survived is not None and survived.threat_id == keeper.id


async def test_regroup_rejects_a_no_op_and_a_missing_target(client):
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    threat, ev = await _threat_with_event(s, d)

    same = await c.patch(f"/admin/events/{ev.id}/threat",
                         json={"threat_id": threat.id}, headers=headers)
    assert same.status_code == 400
    missing = await c.patch(f"/admin/events/{ev.id}/threat",
                            json={"threat_id": 9999}, headers=headers)
    assert missing.status_code == 400


async def test_regroup_refuses_to_group_a_sighting_into_an_impact(client):
    """An impact is a terminal marker, not a path — and it is withheld from the
    map by design, so a sighting moved into one would simply vanish."""
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    impact = Threat(target_type="shahed", status="destroyed", kind="impact")
    s.add(impact)
    await s.commit()
    _threat, ev = await _threat_with_event(s, d)

    r = await c.patch(f"/admin/events/{ev.id}/threat",
                      json={"threat_id": impact.id}, headers=headers)
    assert r.status_code == 400


async def test_regroup_requires_admin(client):
    c, s = client
    d = await _district(s)
    _threat, ev = await _threat_with_event(s, d)
    r = await c.patch(f"/admin/events/{ev.id}/threat", json={"threat_id": None})
    assert r.status_code in (401, 403)


async def test_admin_can_load_a_closed_track_the_public_route_hides(client):
    """The editor opens on tracks the public API will not serve — closed ones,
    and impacts. Impact privacy is a rule about the public map/feed/journal
    (test_impact_privacy.py), not about the operator's own console."""
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    impact = Threat(target_type="shahed", status="destroyed", kind="impact",
                    closed_at=utcnow())
    s.add(impact)
    await s.commit()
    s.add(ThreatEvent(threat_id=impact.id, district_id=d.id, raw_text="влучання"))
    await s.commit()

    assert (await c.get(f"/threats/{impact.id}/events")).status_code == 404
    r = await c.get(f"/admin/threats/{impact.id}", headers=headers)
    assert r.status_code == 200
    assert len(r.json()["events"]) == 1


async def test_track_detail_requires_admin(client):
    c, s = client
    d = await _district(s)
    threat, _ = await _threat_with_event(s, d)
    assert (await c.get(f"/admin/threats/{threat.id}")).status_code in (401, 403)


async def test_manual_attack_type_overrides_the_derived_one(client):
    """PATCH /admin/incidents/{id}/type — the operator's verdict on a raid.

    Both published fields have to move: `target_type` (the label) and
    `classification` (derived from attack_types by domain/attack.classify).
    Setting only the first would leave the banner announcing 'combined' over an
    attack the operator just called ballistic, which is the mismatch the
    override exists to fix.
    """
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    inc = Incident(target_type="shahed", attack_types=["shahed", "missile"])
    s.add(inc)
    await s.commit()
    await _threat_with_event(s, d, target_type="shahed", incident=inc)

    assert (await c.get("/incidents/active")).json()[0]["classification"] == "combined"

    r = await c.patch(
        f"/admin/incidents/{inc.id}/type", json={"target_types": ["ballistic"]}, headers=headers
    )
    assert r.status_code == 200
    assert r.json()["target_type"] == "ballistic"
    assert r.json()["classification"] == "ballistic"
    assert r.json()["type_override"] == ["ballistic"]

    live = (await c.get("/incidents/active")).json()[0]
    assert live["target_type"] == "ballistic"
    assert live["classification"] == "ballistic"


async def test_manual_attack_type_survives_a_new_member_track(client):
    """The whole reason it is a stored column. `recompute_incident_types` runs on
    every attach, so a plain write to `target_type` would be erased by the next
    sighting — seconds away during a live raid."""
    from app.domain.incidents import attach_to_incident

    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    inc = Incident(target_type="shahed", attack_types=["shahed"])
    s.add(inc)
    await s.commit()
    await _threat_with_event(s, d, target_type="shahed", incident=inc)

    await c.patch(
        f"/admin/incidents/{inc.id}/type", json={"target_types": ["ballistic"]}, headers=headers
    )

    # A fresh shahed sighting joins the attack, exactly as the live pipeline does.
    newcomer, _ = await _threat_with_event(s, d, target_type="shahed")
    await attach_to_incident(s, newcomer, utcnow())

    await s.refresh(inc)
    assert inc.target_type == "ballistic"
    assert inc.attack_types == ["ballistic"]
    assert (await c.get("/incidents/active")).json()[0]["classification"] == "ballistic"


async def test_clearing_the_override_returns_to_the_derived_type(client):
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    inc = Incident(target_type="shahed", attack_types=["shahed"])
    s.add(inc)
    await s.commit()
    await _threat_with_event(s, d, target_type="shahed", incident=inc)

    await c.patch(
        f"/admin/incidents/{inc.id}/type", json={"target_types": ["ballistic"]}, headers=headers
    )
    r = await c.patch(
        f"/admin/incidents/{inc.id}/type", json={"target_types": []}, headers=headers
    )
    assert r.status_code == 200
    assert r.json()["type_override"] is None
    # Back to what the members say.
    assert r.json()["target_type"] == "shahed"
    assert r.json()["classification"] == "drone"


async def test_manual_attack_type_leaves_the_member_tracks_alone(client):
    """A verdict on the raid is not a verdict on each sighting: rewriting the
    tracks would make the map and the regression dataset claim a spotter said
    something they did not."""
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    inc = Incident(target_type="shahed", attack_types=["shahed"])
    s.add(inc)
    await s.commit()
    threat, _ = await _threat_with_event(s, d, target_type="shahed", incident=inc)

    await c.patch(
        f"/admin/incidents/{inc.id}/type", json={"target_types": ["ballistic"]}, headers=headers
    )

    await s.refresh(threat)
    assert threat.target_type == "shahed"
    # And no correction was harvested — this is a rollup judgement, not a
    # labelled example of a misread message.
    from app.models import ParserCorrection

    assert await s.scalar(select(func.count()).select_from(ParserCorrection)) == 0


async def test_retype_unknown_incident_404(client):
    c, s = client
    headers = await _admin_headers(s)
    r = await c.patch(
        "/admin/incidents/999999/type", json={"target_types": ["ballistic"]}, headers=headers
    )
    assert r.status_code == 404


async def test_manual_combined_attack(client):
    """A raid of several weapon families reads as 'комбінована', and the operator
    has to be able to say so.

    This is why the override is a LIST. `attack.classify` calls it combined only
    when it sees ≥2 families, and 'combined' is a derived LABEL — not a member of
    the TargetType enum — so no single value could ever have expressed it.
    """
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    inc = Incident(target_type="shahed", attack_types=["shahed"])
    s.add(inc)
    await s.commit()
    await _threat_with_event(s, d, target_type="shahed", incident=inc)

    assert (await c.get("/incidents/active")).json()[0]["classification"] == "drone"

    r = await c.patch(
        f"/admin/incidents/{inc.id}/type",
        json={"target_types": ["shahed", "ballistic"]},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["classification"] == "combined"
    # Labelled by the most dangerous of them, same rule the derived path uses.
    assert r.json()["target_type"] == "ballistic"
    assert r.json()["attack_types"] == ["shahed", "ballistic"]
    assert r.json()["type_override"] == ["shahed", "ballistic"]

    live = (await c.get("/incidents/active")).json()[0]
    assert live["classification"] == "combined"


async def test_two_types_of_one_family_are_not_combined(client):
    """Shahed and a jet drone are both drones. Deriving that stays classify's
    job — the override must not turn "two types" into "combined" by itself."""
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    inc = Incident(target_type="shahed", attack_types=["shahed"])
    s.add(inc)
    await s.commit()
    await _threat_with_event(s, d, target_type="shahed", incident=inc)

    r = await c.patch(
        f"/admin/incidents/{inc.id}/type",
        json={"target_types": ["shahed", "jet_drone"]},
        headers=headers,
    )
    assert r.json()["classification"] == "drone"
    assert r.json()["target_type"] == "jet_drone"


async def test_combined_override_survives_a_new_member_track(client):
    from app.domain.incidents import attach_to_incident

    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    inc = Incident(target_type="shahed", attack_types=["shahed"])
    s.add(inc)
    await s.commit()
    await _threat_with_event(s, d, target_type="shahed", incident=inc)
    await c.patch(
        f"/admin/incidents/{inc.id}/type",
        json={"target_types": ["shahed", "ballistic"]},
        headers=headers,
    )

    newcomer, _ = await _threat_with_event(s, d, target_type="missile")
    await attach_to_incident(s, newcomer, utcnow())

    await s.refresh(inc)
    assert inc.attack_types == ["shahed", "ballistic"]
    assert (await c.get("/incidents/active")).json()[0]["classification"] == "combined"


async def test_unknown_drops_out_of_a_manual_set(client):
    """'unknown' carries no weapon family, so it can't make an attack combined
    and must not sit in attack_types pretending to."""
    c, s = client
    headers = await _admin_headers(s)
    d = await _district(s)
    inc = Incident(target_type="shahed", attack_types=["shahed"])
    s.add(inc)
    await s.commit()
    await _threat_with_event(s, d, target_type="shahed", incident=inc)

    r = await c.patch(
        f"/admin/incidents/{inc.id}/type",
        json={"target_types": ["unknown", "missile"]},
        headers=headers,
    )
    assert r.json()["attack_types"] == ["missile"]
    assert r.json()["classification"] == "cruise_missile"

    # Only 'unknown' named: an override that says nothing about a family.
    r = await c.patch(
        f"/admin/incidents/{inc.id}/type", json={"target_types": ["unknown"]}, headers=headers
    )
    assert r.json()["attack_types"] == []
    assert r.json()["target_type"] == "unknown"
    assert r.json()["classification"] == "unknown"
    # Still an override, not a fall-back to the members' 'shahed'.
    assert r.json()["type_override"] == ["unknown"]

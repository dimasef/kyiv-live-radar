"""Impact markers must never be published while an attack is live.

Where a strike landed is battle-damage assessment for whoever launched it, so
the whole live surface — map, feed, attack banner, per-threat lookup — reports
nothing about impacts. They stay in the DB and surface only in the journal,
once the air-raid alert is over. Each test below pins one of those exits.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.api.serialize import incident_out
from app.auth.security import encode_access
from app.config import settings
from app.domain.journal import KYIV
from app.models import (
    AftermathReport,
    Alert,
    District,
    Incident,
    Source,
    Threat,
    ThreatEvent,
    User,
)


async def _district(session, name_uk="Дарницький", name_en="Darnytskyi") -> District:
    d = District(name_uk=name_uk, name_en=name_en, lat=50.40, lon=30.63)
    session.add(d)
    await session.commit()
    return d


async def _threat(session, district, *, kind="track", status="tracking", when=None,
                  target_type="ballistic"):
    when = when or datetime.now(UTC).replace(tzinfo=None)
    th = Threat(
        target_type=target_type, status=status, kind=kind,
        created_at=when, closed_at=when if kind == "impact" else None,
    )
    session.add(th)
    await session.commit()
    ev = ThreatEvent(
        threat_id=th.id, district_id=district.id, raw_text="влучання по будівлі",
        event_time=when,
    )
    session.add(ev)
    await session.commit()
    return th, ev


async def test_impact_is_absent_from_the_live_map(client, session):
    c, s = client, session
    d = await _district(s)
    live, _ = await _threat(s, d)
    impact, _ = await _threat(s, d, kind="impact", status="impact")

    r = await c.get("/threats/active")
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()}
    assert live.id in ids
    assert impact.id not in ids


async def test_impact_event_is_absent_from_the_feed(client, session):
    c, s = client, session
    d = await _district(s)
    live, live_ev = await _threat(s, d)
    _impact, impact_ev = await _threat(s, d, kind="impact", status="impact")

    r = await c.get("/events/recent")
    assert r.status_code == 200
    event_ids = {e["event"]["id"] for e in r.json()}
    assert live_ev.id in event_ids
    assert impact_ev.id not in event_ids


async def test_impact_events_cannot_be_fetched_by_threat_id(client, session):
    c, s = client, session
    d = await _district(s)
    live, _ = await _threat(s, d)
    impact, _ = await _threat(s, d, kind="impact", status="impact")

    assert (await c.get(f"/threats/{live.id}/events")).status_code == 200
    # Not 200-with-empty-list: the district must not be inferable at all.
    assert (await c.get(f"/threats/{impact.id}/events")).status_code == 404


async def test_incident_publishes_no_impact_count_or_impact_districts(client, session):
    _c, s = client, session
    hit_only = await _district(s, "Дніпровський", "Dniprovskyi")
    seen = await _district(s, "Оболонський", "Obolonskyi")
    # A one-track shahed attack: notable ONLY because something landed, so the
    # flag proves the impact signal survived the count being zeroed.
    inc = Incident(started_at=datetime(2026, 8, 1, 0, 18),
                   last_activity_at=datetime(2026, 8, 1, 0, 18),
                   target_type="shahed")
    s.add(inc)
    await s.commit()
    track, _ = await _threat(s, seen, target_type="shahed")
    impact, _ = await _threat(s, hit_only, kind="impact", status="impact",
                              target_type="shahed")
    for th in (track, impact):
        th.incident_id = inc.id
    await s.commit()
    await s.refresh(inc, ["threats"])
    for th in inc.threats:
        await s.refresh(th, ["events"])

    out = incident_out(inc, sentinel_district_id=None)
    assert out.track_count == 1
    assert out.impact_count == 0
    # The district that ONLY appears because something landed there is the leak
    # this guards: it must not show up in the attack's district list.
    assert out.district_ids == [seen.id]
    assert out.district_count == 1
    # A hit still makes the attack banner-worthy — the signal survives, the
    # number and the place don't.
    assert out.notable


async def test_journal_hides_todays_impacts_only_while_the_alert_is_open(client, session):
    c, s = client, session
    d = await _district(s)
    # Timestamps are stored naive-UTC, but the journal buckets days in
    # Europe/Kyiv — so the day KEYS must be Kyiv dates too. Using the UTC date
    # made this fail for the 3 h each night when Kyiv is already tomorrow.
    now = datetime.now(UTC)
    today, today_key = now.replace(tzinfo=None), now.astimezone(KYIV).date()
    await _threat(s, d, kind="impact", status="impact", when=today)
    yesterday, yesterday_key = today - timedelta(days=1), today_key - timedelta(days=1)
    await _threat(s, d, kind="impact", status="impact", when=yesterday)
    alert = Alert(scope="city", alert_type="air_raid", started_at=today, provider="telegram")
    s.add(alert)
    await s.commit()

    def _impacts(payload):
        return {day["date"]: day["impact_count"] for day in payload["days"]}

    during = _impacts((await c.get("/journal/days")).json())
    assert during[today_key.isoformat()] == 0
    # Only TODAY is withheld — a finished day is history and reports normally.
    assert during[yesterday_key.isoformat()] == 1

    alert.ended_at = today + timedelta(minutes=30)
    alert.closed_reason = "official"
    await s.commit()

    after = _impacts((await c.get("/journal/days")).json())
    assert after[today_key.isoformat()] == 1


# --- The one deliberate exception: GET /threats/impacts (models.IMPACT_ROLES).
# Everything above stays true for everyone else, which is why the hole is its
# own route rather than a branch inside the public ones.


async def _token(session, role: str) -> str:
    user = User(email=f"{role}@x.com", role=role, password_hash="x")
    session.add(user)
    await session.commit()
    return encode_access(user)


async def _an_impact(session) -> Threat:
    d = District(name_uk="Дарницький", name_en="Darnytskyi", lat=50.4, lon=30.6)
    src = Source(channel_key="klr", name="Kyiv Live Radar", role="spotter")
    session.add_all([d, src])
    await session.commit()
    th = Threat(target_type="shahed", status="impact", kind="impact",
                closed_at=datetime.now(UTC))
    session.add(th)
    await session.commit()
    # `source_id` is not decoration — it is the whole point. A NULL many-to-one
    # never emits a lazy query, so an impact with no source silently skipped the
    # one line of `event_out` that touches `ThreatEvent.source`. That is how the
    # route managed to 500 on every REAL impact from 0.49.0 to 0.54.1 while
    # these tests stayed green.
    session.add(ThreatEvent(threat_id=th.id, district_id=d.id, raw_text="влучання",
                            source_id=src.id))
    await session.commit()
    return th


async def test_impact_layer_is_closed_to_everyone_but_vouched_accounts(client, session):
    c, s = client, session
    await _an_impact(s)

    assert (await c.get("/threats/impacts")).status_code == 401

    user = await _token(s, "user")
    r = await c.get("/threats/impacts", headers={"Authorization": f"Bearer {user}"})
    assert r.status_code == 403

    for role in ("observer", "admin", "admin_g"):
        tok = await _token(s, role)
        r = await c.get("/threats/impacts", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200, role
        assert len(r.json()) == 1, role


async def test_the_impact_layer_widens_nothing_else(client, session):
    """An observer is not an admin, and the public map stays public-shaped."""
    c, s = client, session
    await _an_impact(s)
    tok = await _token(s, "observer")
    h = {"Authorization": f"Bearer {tok}"}

    # The live map still withholds it, token or not.
    assert (await c.get("/threats/active", headers=h)).json() == []
    assert (await c.get("/events/recent", headers=h)).json() == []
    # And the console stays shut.
    assert (await c.get("/raw_messages", headers=h)).status_code == 403


async def test_a_dismissed_impact_is_not_served_to_the_layer(client, session):
    c, s = client, session
    th = await _an_impact(s)
    th.closed_reason = "dismissed"
    await s.commit()
    tok = await _token(s, "observer")
    r = await c.get("/threats/impacts", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200 and r.json() == []


async def test_the_layer_only_reaches_back_its_window(client, session):
    c, s = client, session
    th = await _an_impact(s)
    th.created_at = datetime.now(UTC) - timedelta(hours=settings.consequence_layer_hours + 1)
    await s.commit()
    tok = await _token(s, "observer")
    r = await c.get("/threats/impacts", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200 and r.json() == []


# --- …and the same door for the other half of the layer: GET /aftermath.
# A report says what a strike DID to a raion, which on the night of a raid is
# the same battle-damage assessment a strike pin is — so it gets the same gate,
# the same window, and the same three tests that can actually fail. Two more
# were considered and left out on purpose: "absent from /events/recent" and
# "never broadcast over the websocket" are structurally impossible (another
# table; no such WSMessage variant exists), and a test that cannot fail is not
# a pinned intention.


async def _an_aftermath(session) -> AftermathReport:
    d = await session.scalar(select(District).where(District.name_en == "Darnytskyi"))
    if d is None:
        d = District(name_uk="Дарницький", name_en="Darnytskyi", lat=50.4, lon=30.6)
        session.add(d)
        await session.commit()
    report = AftermathReport(
        district_id=d.id, region="kyiv", categories=["fire", "casualties"],
        text="Пожежа у Дарницькому районі після удару",
    )
    session.add(report)
    await session.commit()
    return report


async def test_aftermath_is_closed_to_everyone_but_vouched_accounts(client, session):
    c, s = client, session
    await _an_aftermath(s)

    assert (await c.get("/aftermath")).status_code == 401

    user = await _token(s, "user")
    r = await c.get("/aftermath", headers={"Authorization": f"Bearer {user}"})
    assert r.status_code == 403

    for role in ("observer", "admin", "admin_g"):
        tok = await _token(s, role)
        r = await c.get("/aftermath", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200, role
        body = r.json()
        assert len(body) == 1, role
        # The marker is placeable and labelled without a second request — the
        # last category is the most consequential one (domain/aftermath.py).
        assert body[0]["lat"] == 50.4 and body[0]["district_name"] == "Дарницький"
        assert body[0]["categories"][-1] == "casualties"


async def test_a_dismissed_report_is_not_served(client, session):
    c, s = client, session
    report = await _an_aftermath(s)
    report.dismissed_at = datetime.now(UTC)
    await s.commit()
    tok = await _token(s, "observer")
    r = await c.get("/aftermath", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200 and r.json() == []


async def test_aftermath_only_reaches_back_its_window(client, session):
    c, s = client, session
    report = await _an_aftermath(s)
    report.reported_at = datetime.now(UTC) - timedelta(
        hours=settings.consequence_layer_hours + 1
    )
    await s.commit()
    tok = await _token(s, "observer")
    r = await c.get("/aftermath", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200 and r.json() == []


async def test_the_journal_reports_aftermath_but_not_during_the_raid(client, session):
    """The one surface where a consequence reaches everybody — and only after
    the відбій, under the same rule as `impact_count`.

    Publishing it at all is deliberate: these reports are news posts from public
    channels, and by the time the alert is over the withholding protects
    nothing. During the raid it protects a great deal, which is why today's
    counts read 0 while the siren runs. Counts only either way — the journal
    never says which raion burned.
    """
    c, s = client, session
    d = await _district(s)
    now = datetime.now(UTC)
    today, today_key = now.replace(tzinfo=None), now.astimezone(KYIV).date()
    yesterday, yesterday_key = today - timedelta(days=1), today_key - timedelta(days=1)
    for when in (today, yesterday):
        s.add(AftermathReport(district_id=d.id, region="kyiv", reported_at=when,
                              categories=["fire", "casualties"], text="Пожежа після удару"))
    alert = Alert(scope="city", alert_type="air_raid", started_at=today, provider="telegram")
    s.add(alert)
    await s.commit()

    def _counts(payload):
        return {day["date"]: day["aftermath_count"] for day in payload["days"]}

    during = _counts((await c.get("/journal/days")).json())
    assert during[today_key.isoformat()] == 0
    # Yesterday is untouched: the withholding is about the raid in progress.
    assert during[yesterday_key.isoformat()] == 1

    alert.ended_at = today + timedelta(minutes=30)
    alert.closed_reason = "official"
    await s.commit()

    after = (await c.get("/journal/days")).json()
    assert _counts(after)[today_key.isoformat()] == 1
    today_row = next(day for day in after["days"] if day["date"] == today_key.isoformat())
    assert today_row["aftermath_counts"]["fire"] == 1
    assert today_row["aftermath_counts"]["casualties"] == 1
    # No raion is named — the whole point of aggregating.
    assert "aftermath_district_ids" not in today_row


async def test_a_dismissed_report_never_reaches_the_journal(client, session):
    """An admin-cancelled false positive is excluded from every tally, the same
    way a dismissed track and a dismissed impact are."""
    c, s = client, session
    d = await _district(s)
    now = datetime.now(UTC).replace(tzinfo=None)
    s.add(AftermathReport(district_id=d.id, region="kyiv", reported_at=now,
                          categories=["fire"], text="хибний", dismissed_at=now))
    await s.commit()
    days = (await c.get("/journal/days")).json()["days"]
    assert all(day["aftermath_count"] == 0 for day in days)

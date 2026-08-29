"""Tests for Phase 3 attack classification: attack_types accumulation,
combined classification, the decoy modifier, alert adoption/linking, and the
alert-end-ends-the-attack lifecycle (app/attack.py, app/incidents.py,
app/alerts.py, ingest.py's alert-end branch).
"""

from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.domain.attack import classify
from app.gazetteer import SOURCES
from app.models import Alert, District, Incident, Source, Threat
from app.parsing import DistrictMatcher
from app.pipeline.ingest import ingest_alert_message, ingest_message
from tests.conftest import district_rows

BASE = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def ctx(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'t.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        s.add_all(district_rows())
        s.add_all(Source(channel_key=x["channel_key"], name=x["name"],
                         trust_weight=x.get("trust_weight", 1.0), role=x.get("role", "spotter"))
                  for x in SOURCES)
        await s.commit()
        districts = list(await s.scalars(select(District)))
        sources = list(await s.scalars(select(Source)))
        matcher = DistrictMatcher(districts)
        yield s, matcher, sources
    await engine.dispose()


async def _one_incident(s) -> Incident:
    return (await s.scalars(select(Incident))).one()


# --- attack_types accumulation / classification ---

async def test_attack_types_accumulate_across_tracks(ctx):
    s, m, src = ctx
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Реактивний БпЛА на Позняках", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[0].id, message_id=2)
    inc = await _one_incident(s)
    assert set(inc.attack_types) == {"shahed", "jet_drone"}


async def test_untyped_callout_inherits_a_single_family_incident_type(ctx):
    # The 07-18 case this fallback exists for: per-channel window (5 min) expired,
    # incident is one family -> a bare toponym from the OTHER channel still types.
    s, m, src = ctx
    await ingest_message(s, text="Балістика на Троєщину", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Оболонь", matcher=m, when=BASE + timedelta(minutes=8),
                         source_id=src[1].id, message_id=2)
    obolon = (await s.scalars(
        select(Threat).where(Threat.target_type == "ballistic"))).all()
    assert len(obolon) == 2  # both tracks ballistic


async def test_a_finished_phase_stops_typing_the_one_running_now(ctx):
    # Live 2026-08-19: the raid opened with a ballistic salvo at 20:52 and was
    # still labelling cruise callouts «балістика» at 22:27, because the incident
    # label only ratchets up and never forgets. The prior reads the tracks that
    # are actually flying, so once the salvo is an hour stale it stops speaking.
    s, m, src = ctx
    await ingest_message(s, text="Балістика на Троєщину", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Крилата ракета на Васильків", matcher=m,
                         when=BASE + timedelta(minutes=25), source_id=src[0].id, message_id=2)
    await ingest_message(s, text="Обухів", matcher=m, when=BASE + timedelta(minutes=33),
                         source_id=src[1].id, message_id=3)
    obukhiv = (await s.scalars(select(Threat).order_by(Threat.id.desc()))).first()
    assert obukhiv.target_type == "missile"  # the cruise phase, not the old salvo


async def test_untyped_callout_stays_unknown_in_a_combined_incident(ctx):
    # 08-04: inc.target_type only ratchets up, so one Циркон track made every
    # later untyped callout ballistic. Combined raid -> the incident can't say.
    s, m, src = ctx
    await ingest_message(s, text="Балістика на Троєщину", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Реактивний БпЛА на Позняках", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[0].id, message_id=2)
    await ingest_message(s, text="Оболонь", matcher=m, when=BASE + timedelta(minutes=8),
                         source_id=src[1].id, message_id=3)
    inc = await _one_incident(s)
    assert set(inc.attack_types) == {"ballistic", "jet_drone"}  # combined
    types = {t.target_type for t in await s.scalars(select(Threat))}
    assert "unknown" in types, types  # the bare "Оболонь" was not typed ballistic


async def test_missile_and_ballistic_still_count_as_one_family(ctx):
    # missile -> ballistic is one family (ingest._upgrade_type), not combined.
    s, m, src = ctx
    await ingest_message(s, text="Балістика на Троєщину", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Ракета на Позняки", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[0].id, message_id=2)
    await ingest_message(s, text="Оболонь", matcher=m, when=BASE + timedelta(minutes=8),
                         source_id=src[1].id, message_id=3)
    types = {t.target_type for t in await s.scalars(select(Threat))}
    assert "unknown" not in types, types


async def test_single_family_classification(ctx):
    s, m, src = ctx
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    inc = await _one_incident(s)
    cls = classify(inc.attack_types, inc.decoy_mentions, inc.has_hypersonic)
    assert cls.label == "drone"


async def test_upgrade_does_not_read_as_false_combined(ctx):
    # A SINGLE target refined mid-flight (missile -> ballistic) must leave ONE
    # type on the incident, not both — otherwise it falsely reads as 'combined'
    # (the old append-only attack_types bug; now recomputed from members).
    s, _m, _src = ctx
    from app.domain.incidents import attach_to_incident

    t = Threat(target_type="missile", status="tracking")
    s.add(t)
    await s.commit()
    inc = await attach_to_incident(s, t, BASE)
    assert set(inc.attack_types) == {"missile"}

    t.target_type = "ballistic"
    await s.commit()
    inc = await attach_to_incident(s, t, BASE + timedelta(minutes=1))
    assert set(inc.attack_types) == {"ballistic"}
    assert classify(inc.attack_types, inc.decoy_mentions, inc.has_hypersonic).label == "ballistic"


async def test_combined_classification_across_families(ctx):
    # A shahed track and a ballistic city-wide alert in the same incident
    # window is a genuinely combined raid, not just "ballistic".
    s, m, src = ctx
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Балістика на Київ", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[0].id, message_id=2)
    inc = await _one_incident(s)
    cls = classify(inc.attack_types, inc.decoy_mentions, inc.has_hypersonic)
    assert cls.label == "combined"


async def test_decoy_modifier_does_not_replace_classification(ctx):
    # decoy_suspected is a boolean MODIFIER alongside the real classification,
    # not a replacement label — a raid can be ballistic AND partly imitation.
    s, m, src = ctx
    await ingest_message(
        s, text="Балістика! Курс на Київ, ймовірно імітація удару", matcher=m, when=BASE,
        source_id=src[0].id, message_id=1,
    )
    inc = await _one_incident(s)
    assert inc.decoy_mentions == 1
    cls = classify(inc.attack_types, inc.decoy_mentions, inc.has_hypersonic)
    assert cls.label == "ballistic"
    assert cls.decoy_suspected is True


async def test_hypersonic_flag_accumulates(ctx):
    s, m, src = ctx
    await ingest_message(s, text="Кинджал на Київ!", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    inc = await _one_incident(s)
    assert inc.has_hypersonic is True


# --- Alert adoption / linking (the ballistic-precedes-siren exception) ---

async def test_alert_adopts_a_recent_unlinked_ballistic_incident(ctx):
    # Real sequence: the incident starts (sub-minute ballistic flight time)
    # BEFORE the official siren fires.
    s, m, src = ctx
    await ingest_message(s, text="Балістика на Київ", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    inc = await _one_incident(s)
    assert inc.alert_id is None

    await ingest_alert_message(
        s, text="‼️УВАГА! У Києві оголошена повітряна тривога!",
        when=BASE + timedelta(minutes=5), message_id=100,
    )
    alert = (await s.scalars(select(Alert))).one()
    await s.refresh(inc)
    assert inc.alert_id == alert.id


async def test_alert_does_not_adopt_an_incident_outside_the_lookback_window(ctx):
    s, m, src = ctx
    await ingest_message(s, text="Балістика на Київ", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_alert_message(
        s, text="‼️УВАГА! У Києві оголошена повітряна тривога!",
        # past alert_adopt_lookback_minutes=10
        when=BASE + timedelta(minutes=15), message_id=100,
    )
    inc = await _one_incident(s)
    assert inc.alert_id is None


async def test_new_incident_links_an_already_open_city_alert(ctx):
    s, m, src = ctx
    await ingest_alert_message(
        s, text="‼️УВАГА! У Києві оголошена повітряна тривога!", when=BASE, message_id=100,
    )
    alert = (await s.scalars(select(Alert))).one()
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[0].id, message_id=1)
    inc = await _one_incident(s)
    assert inc.alert_id == alert.id


# --- Alert end ends the attack ---

async def test_alert_end_ends_the_attack(ctx):
    s, m, src = ctx
    await ingest_alert_message(
        s, text="‼️УВАГА! У Києві оголошена повітряна тривога!", when=BASE, message_id=100,
    )
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[0].id, message_id=1)
    track = (await s.scalars(select(Threat))).one()
    assert track.closed_at is None

    await ingest_alert_message(
        s, text="❕Відбій повітряної тривоги!", when=BASE + timedelta(minutes=10), message_id=101,
    )
    await s.refresh(track)
    inc = await _one_incident(s)
    assert track.closed_at is not None and track.closed_reason == "all_clear"
    assert inc.ended_at is not None and inc.ended_reason == "alert_end"


async def test_official_and_spotter_vidbiy_seconds_apart_dedupe(ctx):
    s, m, src = ctx
    await ingest_alert_message(
        s, text="‼️УВАГА! У Києві оголошена повітряна тривога!", when=BASE, message_id=100,
    )
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[0].id, message_id=1)

    await ingest_alert_message(
        s, text="❕Відбій повітряної тривоги!", when=BASE + timedelta(minutes=10), message_id=101,
    )
    inc = await _one_incident(s)
    assert inc.ended_reason == "alert_end"

    # A spotter відбій seconds later finds nothing left open — a no-op, not a
    # second closure that overwrites the reason.
    out2 = await ingest_message(s, text="Відбій тривоги", matcher=m,
                                when=BASE + timedelta(minutes=10, seconds=5),
                                source_id=src[0].id, message_id=2)
    await s.refresh(inc)
    assert inc.ended_reason == "alert_end"
    assert [b for b in out2 if b.type == "status"] == []


async def test_scoped_clear_ends_incident_when_nothing_left_flying(ctx):
    """«Відбій балістичної загрози» closes the ballistic tracks; with no other
    open track the ATTACK must end too — a still-active incident (banner +
    raion highlight) after an explicit stand-down read as a bug (2026-07-18)."""
    s, m, src = ctx
    sid = src[0].id
    await ingest_message(s, text="Балістика на Оболонь!", matcher=m, when=BASE,
                         source_id=sid, message_id=1)
    inc = (await s.scalars(select(Incident))).one()
    assert inc.ended_at is None

    results = await ingest_message(s, text="Відбій балістичної загрози.", matcher=m,
                                   when=BASE + timedelta(minutes=2), source_id=sid, message_id=2)
    await s.refresh(inc)
    assert inc.ended_at is not None and inc.ended_reason == "all_clear"
    # the ended incident is broadcast so the frontend banner/highlight clears
    assert any(b.type == "attack" for b in results)


async def test_scoped_clear_keeps_incident_with_other_open_track(ctx):
    """A ballistic stand-down must NOT end a combined attack while a shahed
    track is still open."""
    s, m, src = ctx
    sid = src[0].id
    await ingest_message(s, text="Балістика на Оболонь!", matcher=m, when=BASE,
                         source_id=sid, message_id=1)
    await ingest_message(s, text="Шахед над Троєщиною", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=sid, message_id=2)
    await ingest_message(s, text="Відбій балістичної загрози.", matcher=m,
                         when=BASE + timedelta(minutes=3), source_id=sid, message_id=3)
    inc = (await s.scalars(select(Incident))).one()
    assert inc.ended_at is None


async def test_stand_down_ends_incident(ctx):
    """A full «дорозвідка» stand-down that closes every open track ends the
    attack as well."""
    s, m, src = ctx
    sid = src[0].id
    await ingest_message(s, text="Шахед над Троєщиною", matcher=m, when=BASE,
                         source_id=sid, message_id=1)
    results = await ingest_message(s, text="Дорозвідка. Чисто.", matcher=m,
                                   when=BASE + timedelta(minutes=2), source_id=sid, message_id=2)
    inc = (await s.scalars(select(Incident))).one()
    assert inc.ended_at is not None and inc.ended_reason == "all_clear"
    assert any(b.type == "attack" for b in results)


# --- regions on the incident (migration 0036) ---

async def test_a_track_starts_an_incident_in_its_own_region(ctx):
    """The incident takes the TRACK's region, never the reporting channel's: a
    Kyiv channel narrating the northern approach must not file a Chernihiv
    target under a Kyiv attack."""
    s, _m, _src = ctx
    from app.domain.incidents import attach_to_incident

    t = Threat(target_type="shahed", status="tracking", region="chernihiv")
    s.add(t)
    await s.commit()
    inc = await attach_to_incident(s, t, BASE)
    assert inc.region == "chernihiv"


async def test_two_regions_do_not_share_one_attack(ctx):
    """The grouping window is per region. Globally, a Сумщина sighting joined
    Kyiv's open incident and landed in Kyiv's banner, rollup card and journal
    count."""
    s, _m, _src = ctx
    from app.domain.incidents import attach_to_incident

    kyiv_track = Threat(target_type="shahed", status="tracking", region="kyiv")
    sumy_track = Threat(target_type="shahed", status="tracking", region="sumy")
    s.add_all([kyiv_track, sumy_track])
    await s.commit()

    kyiv_inc = await attach_to_incident(s, kyiv_track, BASE)
    sumy_inc = await attach_to_incident(s, sumy_track, BASE + timedelta(minutes=1))
    assert kyiv_inc.id != sumy_inc.id
    assert {kyiv_inc.region, sumy_inc.region} == {"kyiv", "sumy"}


async def test_a_clear_ends_only_its_own_regions_attack(ctx):
    """Kyiv's official відбій speaks for Kyiv. Ending a northern attack on it
    would be the same mistake as closing a northern track on it."""
    s, _m, _src = ctx
    from app.domain.incidents import attach_to_incident, end_active_incidents

    for region in ("kyiv", "sumy"):
        t = Threat(target_type="shahed", status="tracking", region=region)
        s.add(t)
        await s.commit()
        await attach_to_incident(s, t, BASE)

    ended = await end_active_incidents(s, BASE + timedelta(minutes=5), "alert_end",
                                       region="kyiv")
    assert [i.region for i in ended] == ["kyiv"]
    still_open = list(await s.scalars(select(Incident).where(Incident.ended_at.is_(None))))
    assert [i.region for i in still_open] == ["sumy"]


async def test_an_alert_adopts_only_its_own_regions_incident(ctx):
    """The ballistic adoption on alert start. Reaching across regions would
    hand a northern incident to Kyiv's siren and, through `alert_id`, into
    Kyiv's journal."""
    s, _m, _src = ctx
    from app.domain.alerts import AlertSignal, apply_alert_signal
    from app.domain.incidents import attach_to_incident

    t = Threat(target_type="ballistic", status="tracking", region="sumy")
    s.add(t)
    await s.commit()
    sumy_inc = await attach_to_incident(s, t, BASE)

    alert = await apply_alert_signal(
        s, AlertSignal(scope="city", action="start", when=BASE + timedelta(minutes=1),
                       region="kyiv"))
    assert alert is not None
    await s.refresh(sumy_inc)
    assert sumy_inc.alert_id is None

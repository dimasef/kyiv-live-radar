"""Tests for Phase 3 attack classification: attack_types accumulation,
combined classification, the decoy modifier, alert adoption/linking, and the
alert-end-ends-the-attack lifecycle (app/attack.py, app/incidents.py,
app/alerts.py, ingest.py's alert-end branch).
"""

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.domain.attack import classify
from app.gazetteer import DISTRICTS, SOURCES
from app.models import Alert, District, Incident, Source, Threat
from app.parsing import DistrictMatcher
from app.pipeline.ingest import ingest_alert_message, ingest_message

BASE = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def ctx(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'t.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        s.add_all(District(name_uk=d["name_uk"], name_en=d["name_en"], lat=d["lat"],
                           lon=d["lon"], aliases=d.get("aliases", [])) for d in DISTRICTS)
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


async def test_single_family_classification(ctx):
    s, m, src = ctx
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    inc = await _one_incident(s)
    cls = classify(inc.attack_types, inc.decoy_mentions, inc.has_hypersonic)
    assert cls.label == "drone"


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

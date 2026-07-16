"""Rescue path (app/pipeline/triage._route_rescue + ingest.process_rescued) —
the riskiest consumer, so every gate gets a test."""

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db import Base
from app.gazetteer import DISTRICTS, SOURCES
from app.models import District, Source, Threat, ThreatEvent, RawMessage, utcnow
from app.parsing import DistrictMatcher
from app.pipeline.triage import TriageJob, route_verdict
from tests.conftest import make_verdict


@pytest_asyncio.fixture
async def ctx():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        s.add_all(District(name_uk=d["name_uk"], name_en=d["name_en"], lat=d["lat"],
                           lon=d["lon"], aliases=d.get("aliases", [])) for d in DISTRICTS)
        s.add_all(Source(channel_key=x["channel_key"], name=x["name"],
                         trust_weight=x["trust_weight"]) for x in SOURCES)
        await s.commit()
        matcher = DistrictMatcher(list(await s.scalars(select(District))))
        did = matcher.districts_index[0][0]  # a real, non-sentinel district id
        yield s, matcher, did
    await engine.dispose()


async def _raw_job(session, text, did, when, source_id=1, message_id=100):
    raw = RawMessage(source_id=source_id, message_id=message_id, text=text, event_time=when)
    session.add(raw)
    await session.commit()
    job = TriageJob(raw_id=raw.id, text=text, when=when, source_id=source_id,
                    message_id=message_id, reply_to_message_id=None, forwarded_from_id=None,
                    forwarded_from_channel_id=None, verdict=None)
    return raw, job


async def test_rescue_enabled_creates_track_at_original_time(ctx, monkeypatch):
    session, _, did = ctx
    monkeypatch.setattr(settings, "triage_rescue_enabled", True)
    when = utcnow() - timedelta(minutes=2)
    raw, job = await _raw_job(session, "ціль над районом", did, when)
    verdict = make_verdict(category="localized", surface=True, district_ids=[did],
                           target_type="shahed", status="sighting", confidence=0.9)
    bcs, action, state = await route_verdict(session, raw, job, verdict)
    assert action == "rescued"
    ev = (await session.scalars(select(ThreatEvent))).one()
    assert ev.decision_source == "triage"
    assert ev.district_id == did
    # Original timestamp, not "now".
    assert abs((ev.event_time.replace(tzinfo=timezone.utc) - when).total_seconds()) < 1


async def test_clear_verdict_never_rescues(ctx, monkeypatch):
    session, _, did = ctx
    monkeypatch.setattr(settings, "triage_rescue_enabled", True)
    raw, job = await _raw_job(session, "відбій", did, utcnow())
    verdict = make_verdict(category="localized", surface=True, district_ids=[did],
                           status="clear", confidence=0.95)
    bcs, action, state = await route_verdict(session, raw, job, verdict)
    assert action == "rescue_candidate"
    assert await session.scalar(select(func.count()).select_from(ThreatEvent)) == 0


async def test_low_confidence_is_not_rescued(ctx, monkeypatch):
    session, _, did = ctx
    monkeypatch.setattr(settings, "triage_rescue_enabled", True)
    raw, job = await _raw_job(session, "можливо ціль", did, utcnow())
    verdict = make_verdict(category="localized", surface=True, district_ids=[did],
                           target_type="shahed", confidence=0.4)
    bcs, action, state = await route_verdict(session, raw, job, verdict)
    assert action == "rescue_candidate"
    assert await session.scalar(select(func.count()).select_from(ThreatEvent)) == 0


async def test_too_old_rescue_is_late(ctx, monkeypatch):
    session, _, did = ctx
    monkeypatch.setattr(settings, "triage_rescue_enabled", True)
    old = utcnow() - timedelta(minutes=settings.track_stale_minutes + 5)
    raw, job = await _raw_job(session, "ціль над районом", did, old)
    verdict = make_verdict(category="localized", surface=True, district_ids=[did],
                           target_type="shahed", confidence=0.9)
    bcs, action, state = await route_verdict(session, raw, job, verdict)
    assert action == "late"
    assert await session.scalar(select(func.count()).select_from(ThreatEvent)) == 0


async def test_rescue_is_idempotent_when_event_exists(ctx, monkeypatch):
    session, _, did = ctx
    monkeypatch.setattr(settings, "triage_rescue_enabled", True)
    when = utcnow() - timedelta(minutes=2)
    raw, job = await _raw_job(session, "ціль над районом", did, when)
    verdict = make_verdict(category="localized", surface=True, district_ids=[did],
                           target_type="shahed", confidence=0.9)
    # A live message already produced an event for this (source, message_id).
    tr = Threat(target_type="shahed", status="tracking")
    session.add(tr)
    await session.commit()
    session.add(ThreatEvent(threat_id=tr.id, district_id=did, raw_text="x", event_time=when,
                            source_id=job.source_id, source_message_id=job.message_id))
    await session.commit()
    bcs, action, state = await route_verdict(session, raw, job, verdict)
    assert action == "rescued"  # recognized as already-produced
    # No second event created.
    assert await session.scalar(select(func.count()).select_from(ThreatEvent)) == 1

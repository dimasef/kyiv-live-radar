"""Async LLM triage: should_triage gating + route_verdict routing table."""

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db import Base
from app.gazetteer import DISTRICTS, SOURCES
from app.models import District, Notice, RawMessage, Source, ThreatAxis, ThreatEvent, utcnow
from app.parsing import DistrictMatcher, parse_message
from app.pipeline.triage import TriageJob, route_verdict, should_triage
from tests.conftest import make_verdict

BASE = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)


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
        yield s, matcher
    await engine.dispose()


M = DistrictMatcher([{"id": i + 1, **d} for i, d in enumerate(DISTRICTS)])


async def _raw_job(session, text, when=None, source_id=1, message_id=100, verdict=None):
    when = when or utcnow()
    raw = RawMessage(source_id=source_id, message_id=message_id, text=text, event_time=when)
    session.add(raw)
    await session.commit()
    job = TriageJob(raw_id=raw.id, text=text, when=when, source_id=source_id,
                    message_id=message_id, reply_to_message_id=None, forwarded_from_id=None,
                    forwarded_from_channel_id=None, verdict=verdict)
    return raw, job


# --- should_triage ---------------------------------------------------------

def test_should_triage_reuses_inline_verdict():
    parsed = parse_message("Реактивний йде на зниження у районі", M)
    assert should_triage(parsed, "rule", make_verdict(category="directional", surface=True))


def test_should_not_triage_when_inline_localized():
    parsed = parse_message("Реактивний йде на зниження у районі", M)
    assert not should_triage(parsed, "llm", make_verdict())


def test_should_not_triage_directional_already_handled():
    parsed = parse_message("Загроза балістики з Брянська", M)
    assert parsed.directional
    assert not should_triage(parsed, "rule", None)


def test_should_triage_suppressed_but_threat_flavored():
    # An aftermath-suppressed message that still names a weapon — worth a second look.
    parsed = parse_message("Постраждала багатоповерхівка від удару шахеда в Дарниці", M)
    assert not parsed.matched or parsed.aftermath
    # (either suppressed or produced nothing) — should_triage true when threat-flavored
    if parsed.aftermath:
        assert should_triage(parsed, "rule", None)


def test_should_not_triage_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "triage_enabled", False)
    parsed = parse_message("Реактивний йде на зниження у районі", M)
    assert not should_triage(parsed, "rule", make_verdict(surface=True))


# --- route_verdict ---------------------------------------------------------

async def test_route_directional_raises_axis_and_notice(ctx):
    session, _ = ctx
    raw, job = await _raw_job(session, "щось із брянська")
    verdict = make_verdict(category="directional", surface=True, origin_place="bryansk",
                           target_type="ballistic", summary="Балістика з Брянщини")
    bcs, action, state = await route_verdict(session, raw, job, verdict)
    assert action == "axis" and state == "done"
    assert await session.scalar(select(func.count()).select_from(ThreatAxis)) == 1
    notice = (await session.scalars(select(Notice))).one()
    assert notice.kind == "directional" and notice.generated_by == "llm" and notice.origin == "bryansk"


async def test_route_forecast_is_notice_only(ctx):
    session, _ = ctx
    raw, job = await _raw_job(session, "готують масований удар")
    verdict = make_verdict(category="forecast", surface=True, summary="Готують масований удар")
    bcs, action, state = await route_verdict(session, raw, job, verdict)
    assert action == "notice"
    assert await session.scalar(select(func.count()).select_from(ThreatAxis)) == 0
    notice = (await session.scalars(select(Notice))).one()
    assert notice.kind == "forecast" and notice.generated_by == "llm"


async def test_route_noise_suppresses(ctx):
    session, _ = ctx
    raw, job = await _raw_job(session, "реклама каналу")
    bcs, action, state = await route_verdict(session, raw, job, make_verdict(category="noise"))
    assert action == "suppress_confirmed" and bcs == []


async def test_route_stale_verdict_is_audit_only(ctx):
    session, _ = ctx
    old = utcnow() - timedelta(minutes=settings.triage_max_age_minutes + 5)
    raw, job = await _raw_job(session, "щось із брянська", when=old)
    verdict = make_verdict(category="directional", surface=True, origin_place="bryansk")
    bcs, action, state = await route_verdict(session, raw, job, verdict)
    assert action == "late" and bcs == []
    assert await session.scalar(select(func.count()).select_from(ThreatAxis)) == 0


async def test_localized_verdict_is_rescue_candidate_when_disabled(ctx, monkeypatch):
    # The kill-switch still works: with rescue off (it ships ENABLED since the
    # 07-18 audit) a qualifying verdict is only recorded, never acted on.
    session, _ = ctx
    monkeypatch.setattr(settings, "triage_rescue_enabled", False)
    raw, job = await _raw_job(session, "ціль над оболонню")
    verdict = make_verdict(category="localized", surface=True, district_ids=[1],
                           target_type="shahed", confidence=0.9)
    bcs, action, state = await route_verdict(session, raw, job, verdict)
    assert action == "rescue_candidate" and bcs == []
    assert await session.scalar(select(func.count()).select_from(ThreatEvent)) == 0


async def test_reprocess_replay_routes_stored_verdict(ctx):
    # A message with a STORED directional verdict, replayed through process_parsed
    # in 'replay' mode, deterministically rebuilds its axis + notice (no API/queue).
    from app.models import ThreatAxis
    from app.pipeline.ingest import process_parsed

    session, matcher = ctx
    raw = RawMessage(source_id=1, message_id=200, text="щось незрозуміле з брянська",
                     event_time=utcnow())
    raw.llm_response = make_verdict(category="directional", surface=True, origin_place="bryansk",
                                    target_type="ballistic", summary="Балістика з Брянщини")
    session.add(raw)
    await session.commit()
    out = await process_parsed(
        session, raw=raw, text=raw.text, matcher=matcher, when=raw.event_time,
        source_id=1, message_id=200, forwarded_from_id=None,
        forwarded_from_channel_id=None, reply_to_message_id=None, triage="replay",
    )
    assert any(b.type == "axis" for b in out)
    assert await session.scalar(select(func.count()).select_from(ThreatAxis)) == 1
    assert raw.triage_action == "axis"

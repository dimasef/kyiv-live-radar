"""Unit tests for per-source quality metrics (app/api/source_stats.py) — pure DB
aggregation, no HTTP. Verifies each metric and that pre-column history
(llm_attempted IS NULL) is excluded from the LLM-fallback denominator."""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.source_stats import compute_source_stats
from app.db import Base
from app.models import (
    District,
    ParserCorrection,
    RawMessage,
    Source,
    Threat,
    ThreatEvent,
)


@pytest_asyncio.fixture
async def Session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'s.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _seed(Session) -> int:
    async with Session() as s:
        d = District(name_uk="Троєщина", name_en="Troieshchyna", lat=50.5, lon=30.6)
        src = Source(channel_key="chan", name="Chan")
        s.add_all([d, src])
        await s.commit()

        # 4 raw messages: 3 processed; llm_attempted True/False/None across them.
        s.add_all([
            RawMessage(source_id=src.id, message_id=1, text="a", processed=True, llm_attempted=False),
            RawMessage(source_id=src.id, message_id=2, text="b", processed=True, llm_attempted=True),
            RawMessage(source_id=src.id, message_id=3, text="c", processed=True, llm_attempted=None),
            RawMessage(source_id=src.id, message_id=4, text="d", processed=False),
        ])
        await s.commit()
        m1 = await s.scalar(select(RawMessage.id).where(RawMessage.message_id == 1))

        # Two tracks (one conflicted). Events link back to messages 1 & 2 via
        # source_message_id, so those 2 of the 4 messages count as "localized".
        t_clean = Threat(target_type="shahed", status="tracking", has_conflict=False)
        t_conf = Threat(target_type="shahed", status="tracking", has_conflict=True)
        s.add_all([t_clean, t_conf])
        await s.commit()
        s.add_all([
            ThreatEvent(threat_id=t_clean.id, district_id=d.id, source_id=src.id, source_message_id=1),
            ThreatEvent(threat_id=t_clean.id, district_id=d.id, source_id=src.id, source_message_id=2),
            ThreatEvent(threat_id=t_conf.id, district_id=d.id, source_id=src.id, source_message_id=1),
        ])
        # One harvested parser mistake attributable to this source (via m1).
        s.add(ParserCorrection(raw_message_id=m1, text="a", kind="false_positive", expected={}, origin="dismiss"))
        await s.commit()
        return src.id


async def test_metrics(Session):
    src_id = await _seed(Session)
    async with Session() as s:
        stats = await compute_source_stats(s)

    st = stats[src_id]
    assert st.messages_total == 4
    assert st.messages_processed == 3
    assert st.events_produced == 3
    # llm_attempted: True=1 over non-null=2 (the None row is excluded) -> 0.5
    assert st.llm_fallback_rate == pytest.approx(0.5)
    # coverage: 2 of the 4 messages (1 & 2) got localized -> 0.5
    assert st.coverage_rate == pytest.approx(0.5)
    # conflict: 1 event on a conflicted track over 3
    assert st.conflict_share == pytest.approx(1 / 3)
    # corrections: 1 over 3 processed
    assert st.correction_rate == pytest.approx(1 / 3)
    assert st.last_message_at is not None
    assert 0 <= st.quality_score <= 100
    assert st.quality_score == pytest.approx(58.3, abs=0.2)


async def test_llm_rate_none_when_no_column_data(Session):
    """A source whose messages all predate the llm_attempted column has no
    denominator — the rate is None (unknown), not 0."""
    async with Session() as s:
        src = Source(channel_key="old", name="Old")
        s.add(src)
        await s.commit()
        s.add(RawMessage(source_id=src.id, message_id=9, text="x", processed=True, llm_attempted=None))
        await s.commit()
        sid = src.id
        stats = await compute_source_stats(s)
    assert stats[sid].llm_fallback_rate is None


async def test_coverage_is_none_for_alert_channel(Session):
    """Alert channels feed the air-raid parser, not the map — coverage would be a
    misleading 0%, so it's None and doesn't drag their score."""
    async with Session() as s:
        src = Source(channel_key="official", name="Official", role="alert")
        s.add(src)
        await s.commit()
        s.add(RawMessage(source_id=src.id, message_id=1, text="Повітряна тривога", processed=True))
        await s.commit()
        sid = src.id
        stats = await compute_source_stats(s)
    assert stats[sid].coverage_rate is None

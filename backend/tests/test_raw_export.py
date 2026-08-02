"""The /raw debug serialization (api/raw_query.py::serialize_raw_rows).

Everything here exists to make a feed dump readable without a DB session: WHY a
message produced nothing, WHERE its events landed, and WHEN it was actually
stored. Reviewing a 100-message export on 2026-08-02 stalled on all three.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.raw_query import serialize_raw_rows
from app.db import Base
from app.models import District, RawMessage, Source, Threat, ThreatEvent


@pytest_asyncio.fixture
async def session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'t.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        s.add(District(name_uk="Оболонський", name_en="Obolonskyi", lat=50.5, lon=30.5))
        await s.commit()
        yield s
    await engine.dispose()


async def _spotter(session) -> Source:
    src = Source(name="Тест", channel_key="t", role="spotter")
    session.add(src)
    await session.commit()
    return src


async def _raw(session, src, text, *, message_id, reply_to=None, when=None):
    raw = RawMessage(
        source_id=src.id, message_id=message_id, text=text,
        event_time=when or datetime.now(UTC).replace(tzinfo=None),
        reply_to_message_id=reply_to,
    )
    session.add(raw)
    await session.commit()
    return raw


async def _serialize(session, rows):
    return {item.id: item for item in await serialize_raw_rows(session, rows)}


async def test_suppression_reason_is_machine_readable(session):
    src = await _spotter(session)
    promo = await _raw(session, src, "Підтримати банку: https://send.monobank.ua/jar/x",
                       message_id=1)
    pulse = await _raw(session, src, "Ціль!", message_id=2)

    out = await _serialize(session, [promo, pulse])
    assert out[promo.id].suppressed_by == "promo"
    assert out[promo.id].outcome == "реклама/донат"
    # Used to land in the "не про загрозу" catch-all with no way to tell it
    # apart from actual junk.
    assert out[pulse.id].suppressed_by == "target_pulse"


async def test_parsed_snapshot_is_present_even_when_nothing_was_produced(session):
    src = await _spotter(session)
    raw = await _raw(session, src, "2х БПЛА в Оболонському районі", message_id=1)

    parsed = (await _serialize(session, [raw]))[raw.id].parsed
    assert parsed is not None
    assert parsed.target_type == "shahed"
    assert parsed.target_count == 2
    assert parsed.matched and parsed.district_names == ["Оболонський"]


async def test_event_link_carries_the_district_it_landed_on(session):
    src = await _spotter(session)
    raw = await _raw(session, src, "БПЛА Оболонь", message_id=1)
    district = await session.scalar(District.__table__.select().with_only_columns(District.id))
    threat = Threat(target_type="shahed", status="tracking")
    session.add(threat)
    await session.commit()
    session.add(ThreatEvent(
        threat_id=threat.id, district_id=district, raw_text=raw.text,
        source_id=src.id, source_message_id=raw.message_id, decision_source="rule",
    ))
    await session.commit()

    link = (await _serialize(session, [raw]))[raw.id].events[0]
    assert link.district_id == district
    assert link.district_name == "Оболонський"
    assert link.decision_source == "rule"
    assert link.threat_status == "tracking"


async def test_ingestion_lag_and_broken_reply_chain_are_visible(session):
    """The 2026-08-02 failure: a 00:14 message was stored after its own reply
    child, so the child had no parent to thread onto and both became tracks."""
    src = await _spotter(session)
    posted = datetime(2026, 8, 2, 0, 14)
    parent = await _raw(session, src, "Реактивний БПЛА в район Броварів",
                        message_id=5021, when=posted)
    child = await _raw(session, src, "Димерка/Бровари", message_id=5022,
                       reply_to=5021, when=posted + timedelta(minutes=1))
    orphan = await _raw(session, src, "Уважно", message_id=5023, reply_to=9999,
                        when=posted + timedelta(minutes=2))

    out = await _serialize(session, [parent, child, orphan])
    # Stamped at insert time by the column default, so it reads well after the
    # Telegram timestamp — that difference IS the backfill-lag signal.
    assert out[parent.id].ingested_at is not None
    assert out[parent.id].ingested_at.replace(tzinfo=None) > posted
    assert out[child.id].reply_parent_raw_id == parent.id
    # A reply whose parent we never stored: the chain could not be threaded.
    assert out[orphan.id].reply_parent_raw_id is None

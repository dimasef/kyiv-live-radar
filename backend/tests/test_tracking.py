"""End-to-end ingest/tracking tests on a temp SQLite DB (no Telegram needed)."""

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.gazetteer import DISTRICTS, SOURCES
from app.ingest import ingest_message
from app.models import District, RawMessage, Source, Threat, ThreatEvent
from app.parser import DistrictMatcher


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
                         trust_weight=x["trust_weight"]) for x in SOURCES)
        await s.commit()
        districts = list(await s.scalars(select(District)))
        sources = list(await s.scalars(select(Source)))
        matcher = DistrictMatcher(districts)
        yield s, matcher, sources
    await engine.dispose()


BASE = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)


async def _count_threats(s):
    return await s.scalar(select(func.count()).select_from(Threat))


async def test_same_district_corroborates_into_one_track(ctx):
    """Two non-reply reports naming the SAME district in a tight window merge —
    that's corroboration, not two targets."""
    s, m, src = ctx
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Шахед Оболонь", matcher=m,
                         when=BASE + timedelta(minutes=2), source_id=src[0].id, message_id=2)
    assert await _count_threats(s) == 1


async def test_non_reply_different_districts_split(ctx):
    """Non-threaded sightings over DIFFERENT districts no longer collapse onto the
    newest open track — without a reply we can't assume it's the same target."""
    s, m, src = ctx
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Шахед курс на Виноградар", matcher=m,
                         when=BASE + timedelta(minutes=2), source_id=src[0].id, message_id=2)
    assert await _count_threats(s) == 2


async def test_corroboration_respects_window(ctx):
    """Same district but outside the corroboration window -> separate tracks."""
    s, m, src = ctx
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Шахед Оболонь", matcher=m,
                         when=BASE + timedelta(minutes=30), source_id=src[0].id, message_id=2)
    assert await _count_threats(s) == 2


async def test_new_target_starts_new_track(ctx):
    s, m, src = ctx
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Новий шахед на Позняках", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[0].id, message_id=2)
    assert await _count_threats(s) == 2


async def test_gap_starts_new_track(ctx):
    s, m, src = ctx
    await ingest_message(s, text="Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Шахед над Позняками", matcher=m,
                         when=BASE + timedelta(minutes=40), source_id=src[0].id, message_id=2)
    assert await _count_threats(s) == 2


async def test_cross_source_corroboration(ctx):
    s, m, src = ctx
    await ingest_message(s, text="🔴 Шахед над Троєщиною", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Шахед Троєщина", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[1].id, message_id=2)
    t = (await s.scalars(select(Threat))).first()
    await s.refresh(t, ["events"])
    assert t.corroboration_count == 2
    assert t.confidence >= 0.75


async def test_repost_does_not_inflate(ctx):
    s, m, src = ctx
    await ingest_message(s, text="🔴 Шахед над Троєщиною", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=100)
    # Aggregator reposts the SAME original message id -> same origin.
    await ingest_message(s, text="🔁 Шахед над Троєщиною", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[3].id,
                         message_id=101, forwarded_from_id=100)
    t = (await s.scalars(select(Threat))).first()
    await s.refresh(t, ["events"])
    assert t.corroboration_count == 1  # repost collapses to the original origin


async def test_destroyed_closes_track(ctx):
    s, m, src = ctx
    await ingest_message(s, text="🔴 Шахед над Дніпровським районом", matcher=m,
                         when=BASE, source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Збили ціль над Дніпровським районом", matcher=m,
                         when=BASE + timedelta(minutes=2), source_id=src[0].id, message_id=2)
    t = (await s.scalars(select(Threat))).first()
    assert t.status == "destroyed" and t.closed_at is not None


async def test_all_clear_closes_everything(ctx):
    s, m, src = ctx
    await ingest_message(s, text="Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Новий шахед на Позняках", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[0].id, message_id=2)
    out = await ingest_message(s, text="Відбій тривоги в Києві", matcher=m,
                               when=BASE + timedelta(minutes=3), source_id=src[0].id, message_id=3)
    open_left = await s.scalar(
        select(func.count()).select_from(Threat).where(Threat.closed_at.is_(None))
    )
    assert open_left == 0
    assert len(out) == 2  # both tracks closed and broadcast


async def test_destroyed_closes_track_over_named_district(ctx):
    s, m, src = ctx
    # Track A over Оболонь, then a separate new target B over Позняки.
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Новий шахед на Позняках", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[0].id, message_id=2)
    # "збили над Оболонню" must close track A, not the newer track B.
    await ingest_message(s, text="Збили ціль над Оболонню", matcher=m,
                         when=BASE + timedelta(minutes=2), source_id=src[0].id, message_id=3)
    ts = list(await s.scalars(select(Threat).order_by(Threat.id)))
    assert ts[0].closed_at is not None      # A (Оболонь) closed
    assert ts[1].closed_at is None          # B (Позняки) still open


async def test_stale_track_auto_closed(ctx):
    s, m, src = ctx
    from app.tracking import close_stale_tracks
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    # 5 min later — still fresh, not closed.
    assert await close_stale_tracks(s, BASE + timedelta(minutes=5), 20) == []
    # 30 min of silence — auto-closed.
    closed = await close_stale_tracks(s, BASE + timedelta(minutes=30), 20)
    assert len(closed) == 1 and closed[0].status == "lost"


async def test_reply_continues_track_across_gap(ctx):
    """A reply joins its parent's track even past track_gap_minutes — the reply
    thread, not time-proximity, defines the target."""
    s, m, src = ctx
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Курс на Виноградар", matcher=m,
                         when=BASE + timedelta(minutes=40), source_id=src[0].id,
                         message_id=2, reply_to_message_id=1)
    assert await _count_threats(s) == 1


async def test_reply_beats_new_target_wording(ctx):
    """Reply-threading is authoritative: a reply stays on the parent's track even
    if the text reads like a new target."""
    s, m, src = ctx
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Новий шахед на Позняках", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[0].id,
                         message_id=2, reply_to_message_id=1)
    assert await _count_threats(s) == 1


async def test_reply_chain_is_transitive(ctx):
    """A→B(reply A)→C(reply B) is one track, even when each hop exceeds the gap."""
    s, m, src = ctx
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Курс на Виноградар", matcher=m,
                         when=BASE + timedelta(minutes=30), source_id=src[0].id,
                         message_id=2, reply_to_message_id=1)
    await ingest_message(s, text="Вже над Позняками", matcher=m,
                         when=BASE + timedelta(minutes=60), source_id=src[0].id,
                         message_id=3, reply_to_message_id=2)
    assert await _count_threats(s) == 1
    t = (await s.scalars(select(Threat))).first()
    await s.refresh(t, ["events"])
    assert len(t.events) == 3


async def test_reply_scoped_to_source(ctx):
    """Reply ids are per-channel: a reply id from another source must NOT hijack a
    same-numbered message on a different source."""
    s, m, src = ctx
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=5)
    # Different source, reply_to id 5 — no msg 5 exists on src[1], so it must NOT
    # join src[0]'s track. New target with no reply match + is_new_target => new.
    await ingest_message(s, text="Новий шахед на Позняках", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[1].id,
                         message_id=5, reply_to_message_id=5)
    assert await _count_threats(s) == 2


async def test_destroyed_via_reply_closes_that_track(ctx):
    """A 'destroyed' reply closes the track it replies to, not merely the newest —
    even when the destroyed message names no district."""
    s, m, src = ctx
    # Track A over Оболонь, then a separate newer target B over Позняки.
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Новий шахед на Позняках", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[0].id,
                         message_id=2)
    # "Збили" (no district) replying to A's first message must close A, not B.
    await ingest_message(s, text="Збили ✅", matcher=m,
                         when=BASE + timedelta(minutes=2), source_id=src[0].id,
                         message_id=3, reply_to_message_id=1)
    ts = list(await s.scalars(select(Threat).order_by(Threat.id)))
    assert ts[0].status == "destroyed" and ts[0].closed_at is not None  # A
    assert ts[1].closed_at is None                                      # B still open


async def test_target_count_grows_along_reply_chain(ctx):
    """A group's stated count rides one reply-chain track and only grows."""
    s, m, src = ctx
    await ingest_message(s, text="🔴 2х шахеди над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Їх вже 3х, курс на Виноградар", matcher=m,
                         when=BASE + timedelta(minutes=2), source_id=src[0].id,
                         message_id=2, reply_to_message_id=1)
    assert await _count_threats(s) == 1
    t = (await s.scalars(select(Threat))).first()
    assert t.target_count == 3
    # A later message naming fewer must NOT shrink the known group size.
    await ingest_message(s, text="Один ще над Позняками", matcher=m,
                         when=BASE + timedelta(minutes=3), source_id=src[0].id,
                         message_id=3, reply_to_message_id=2)
    await s.refresh(t)
    assert t.target_count == 3


async def test_duplicate_message_id_is_ignored(ctx):
    """Re-ingesting the same (source_id, message_id) — e.g. a repeated Telegram
    backfill on every restart — must be a no-op, not a second raw_message/event
    (root cause of duplicate-looking feed rows with diverging track stats)."""
    s, m, src = ctx
    out1 = await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                                source_id=src[0].id, message_id=42)
    out2 = await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m,
                                when=BASE + timedelta(minutes=5),
                                source_id=src[0].id, message_id=42)
    assert len(out1) == 1
    assert out2 == []
    assert await s.scalar(select(func.count()).select_from(RawMessage)) == 1
    assert await s.scalar(select(func.count()).select_from(ThreatEvent)) == 1
    assert await _count_threats(s) == 1


async def test_duplicate_message_id_scoped_per_source(ctx):
    """The same numeric message_id from a DIFFERENT source is not a duplicate —
    Telegram message ids are only unique within one channel."""
    s, m, src = ctx
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[1].id, message_id=1)
    assert await s.scalar(select(func.count()).select_from(RawMessage)) == 2


async def test_conflict_between_sources(ctx):
    s, m, src = ctx
    await ingest_message(s, text="🔴 Шахед над Осокорками", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Балістика, Осокорки!", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[1].id, message_id=2)
    t = (await s.scalars(select(Threat))).first()
    await s.refresh(t, ["events"])
    assert t.has_conflict  # shahed vs missile on the same track

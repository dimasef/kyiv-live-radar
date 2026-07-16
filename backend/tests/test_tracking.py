"""End-to-end ingest/tracking tests on a temp SQLite DB (no Telegram needed)."""

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.gazetteer import DISTRICTS, SOURCES
from app.models import District, Incident, RawMessage, Source, Threat, ThreatEvent
from app.parsing import DistrictMatcher
from app.pipeline.ingest import ingest_alert_message, ingest_message


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


async def test_event_count_snapshots_running_max_not_final(ctx):
    """A feed event carries the group size KNOWN AS OF that event: an early city
    callout stays ×1 even after a later "3 ракети" grows the alert to ×3 — so the
    feed doesn't retroactively show the final count on the earliest sighting."""
    s, m, src = ctx
    await ingest_message(s, text="Ціль на місто!", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="3 ракети", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[0].id, message_id=2)
    events = list(await s.scalars(select(ThreatEvent).order_by(ThreatEvent.event_time)))
    assert [e.event_target_count for e in events] == [1, 3]
    # ...while the track itself carries the final (max) count.
    threat = (await s.scalars(select(Threat))).one()
    assert threat.target_count == 3


async def test_minus_does_not_close_citywide_alert(ctx):
    """A partial interception ("По ракетам мінус") must NOT close a city-wide
    ballistic alert. Else the next "на місто" callout can't rejoin the just-closed
    alert and spawns a SECOND city-wide track — the live 238/239 split. One
    barrage -> exactly one open city-wide track."""
    s, m, src = ctx
    sid = src[0].id
    await ingest_message(s, text="🚀 Балістика на Київ", matcher=m, when=BASE,
                         source_id=sid, message_id=1)
    await ingest_message(s, text="По ракетам мінус.", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=sid, message_id=2)
    await ingest_message(s, text="Наближення на місто!", matcher=m,
                         when=BASE + timedelta(minutes=2), source_id=sid, message_id=3)
    city = list(await s.scalars(select(Threat).where(Threat.scope == "city")))
    assert len(city) == 1          # no split into 238+239
    assert city[0].closed_at is None  # the мінус did not close it
    n_events = await s.scalar(
        select(func.count()).select_from(ThreatEvent).where(ThreatEvent.threat_id == city[0].id)
    )
    assert n_events == 2           # the two "на місто" callouts, not the мінус


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


async def test_corroboration_matches_latest_position_not_full_history(ctx):
    """A track that has MOVED ON must not keep matching districts it passed
    through earlier — only its current (latest) position corroborates.

    Real failure found via eval/track_eval.py on a real backfill: a long-running
    track that had ever touched a busy corridor district (e.g. Бровари) kept
    absorbing unrelated LATER sightings of that same district for as long as it
    stayed open, snowballing into a mega-track merging several genuinely
    different real targets. Matching against the full event history (instead of
    just the latest one) was the root cause.
    """
    s, m, src = ctx
    # Track A: Оболонь (t=0), replied into by Виноградар (t=1) — one track,
    # reply-linked, now sitting over Виноградар.
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Шахед курс на Виноградар", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[0].id,
                         message_id=2, reply_to_message_id=1)
    assert await _count_threats(s) == 1

    # A later, non-reply sighting of Оболонь — the district A passed through
    # EARLIER, not where it is now — must NOT corroborate onto A.
    await ingest_message(s, text="Шахед Оболонь", matcher=m,
                         when=BASE + timedelta(minutes=2), source_id=src[0].id,
                         message_id=3)
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


async def test_same_source_multiple_messages_does_not_inflate_corroboration(ctx):
    # Real bug found live: a track narrated over 2 messages from the SAME
    # channel ("Один на водосховище" then "Мінуснули, Дорозвідка", both
    # «Віраж Києва») showed corroboration_count=2 — every message has a
    # unique id even within one channel, so keying origin on bare message id
    # made each additional update from the SAME source look independent.
    s, m, src = ctx
    await ingest_message(s, text="🔴 Шахед над Троєщиною", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Збили ціль над Троєщиною", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[0].id, message_id=2)
    t = (await s.scalars(select(Threat))).first()
    await s.refresh(t, ["events"])
    assert t.corroboration_count == 1
    assert t.confidence < 0.75


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


async def test_destroyed_without_district_inherits_last_known_and_creates_event(ctx):
    # Real feed example: "Один збили, залишився ще один" closes the track but
    # names no district of its own — it must still become a real ThreatEvent
    # (inheriting the track's last known district) so the closing message
    # shows up in the feed instead of vanishing with only a status broadcast.
    s, m, src = ctx
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    out = await ingest_message(s, text="Один збили, залишився ще один", matcher=m,
                               when=BASE + timedelta(minutes=1), source_id=src[0].id, message_id=2)
    t = (await s.scalars(select(Threat))).first()
    await s.refresh(t, ["events"])
    assert t.status == "destroyed" and t.closed_at is not None
    assert len(t.events) == 2
    assert t.events[-1].district_id == t.events[0].district_id  # inherited Оболонь
    assert t.events[-1].raw_text == "Один збили, залишився ще один"
    # Must broadcast as 'event' (not 'status') so the frontend feed shows it.
    assert len(out) == 1 and out[0].type == "event" and out[0].event is not None


async def test_lost_signal_type_scoped_closes_only_matching_target_type(ctx):
    # Real feed example: "Дорозвідка по крилатих ракетах" = ППО no longer has
    # missile targets — must close ONLY open missile tracks, leaving a shahed
    # track untouched, and must still create a visible event on the closed one.
    s, m, src = ctx
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Ракета над Позняками", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[0].id, message_id=2)
    out = await ingest_message(s, text="Дорозвідка по крилатих ракетах.", matcher=m,
                               when=BASE + timedelta(minutes=2), source_id=src[0].id, message_id=3)
    shahed_t, missile_t = list(await s.scalars(select(Threat).order_by(Threat.id)))
    assert shahed_t.target_type == "shahed" and missile_t.target_type == "missile"
    assert shahed_t.closed_at is None  # a different target type — untouched
    assert missile_t.closed_at is not None and missile_t.status == "lost"
    await s.refresh(missile_t, ["events"])
    assert len(missile_t.events) == 2  # original sighting + the lost-signal event
    assert len(out) == 1 and out[0].type == "event" and out[0].event is not None


async def test_lost_signal_untyped_closes_all_open_tracks(ctx):
    # "Дорозвідка" with no target type named applies to everything.
    s, m, src = ctx
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Ракета над Позняками", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[0].id, message_id=2)
    out = await ingest_message(s, text="Все, Дорозвідка", matcher=m,
                               when=BASE + timedelta(minutes=2), source_id=src[0].id, message_id=3)
    ts = list(await s.scalars(select(Threat)))
    assert all(t.closed_at is not None and t.status == "lost" for t in ts)
    assert len(out) == 2  # one event per closed track, both visible in the feed
    assert all(b.type == "event" and b.event is not None for b in out)


async def test_lost_signal_does_not_close_a_track_with_a_concurrent_real_sighting(ctx):
    # A "дорозвідка" message that ALSO names a district (a real concurrent
    # sighting of something else) must not close anything.
    s, m, src = ctx
    await ingest_message(s, text="Ракета над Позняками", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(
        s, text="Дорозвідка по крилатим ракетам. Залишаються БПЛА. Найближчий в районі Позняки",
        matcher=m, when=BASE + timedelta(minutes=1), source_id=src[0].id, message_id=2,
    )
    ts = list(await s.scalars(select(Threat)))
    assert all(t.closed_at is None for t in ts)


async def test_lost_signal_does_not_override_destroyed(ctx):
    # Real feed example: "Мінуснули, Дорозвідка" — one target confirmed
    # destroyed. Must close only the matching track as "destroyed", NOT every
    # open track as "lost" (the bug: lost_signal's ingest branch ran before
    # the destroyed branch, so a coincidental "дорозвідка" in a destroyed
    # message wrongly mass-closed everything).
    s, m, src = ctx
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Ракета над Позняками", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[0].id, message_id=2)
    await ingest_message(s, text="Мінуснули, Дорозвідка", matcher=m,
                         when=BASE + timedelta(minutes=2), source_id=src[0].id, message_id=3)
    ts = list(await s.scalars(select(Threat).order_by(Threat.id)))
    # find_open_track (no reply, no named district) picks the most recently
    # active track — only ONE track closes, as "destroyed", the other stays open.
    closed = [t for t in ts if t.closed_at is not None]
    open_ = [t for t in ts if t.closed_at is None]
    assert len(closed) == 1 and closed[0].status == "destroyed"
    assert len(open_) == 1


async def test_spotter_full_vidbiy_is_inert(ctx):
    # A FULL spotter "Відбій тривоги" is NO LONGER authoritative — it must not
    # close tracks nor raise a "Відбій" feed card. The authoritative full
    # all-clear comes only from the official alert channel (see
    # test_official_all_clear_closes_everything below).
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
    assert open_left == 2  # both stay open — a spotter full відбій is inert
    assert [b for b in out if b.type in ("status", "notice")] == []


async def test_official_all_clear_closes_everything(ctx):
    # The authoritative full all-clear: the official alert channel's city end
    # closes every open track and raises the "Відбій" feed card.
    s, m, src = ctx
    await ingest_alert_message(s, text="‼️У Києві оголошена повітряна тривога!",
                               when=BASE, message_id=100)
    await ingest_message(s, text="Шахед над Оболонню", matcher=m,
                         when=BASE + timedelta(seconds=30), source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Новий шахед на Позняках", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[0].id, message_id=2)
    out = await ingest_alert_message(s, text="❕Відбій повітряної тривоги!",
                                     when=BASE + timedelta(minutes=3), message_id=101)
    open_left = await s.scalar(
        select(func.count()).select_from(Threat).where(Threat.closed_at.is_(None))
    )
    assert open_left == 0
    assert len([b for b in out if b.type == "status"]) == 2  # both tracks closed
    notices = [b for b in out if b.type == "notice"]
    assert len(notices) == 1 and notices[0].notice.kind == "clear"  # відбій in feed


async def test_scoped_ballistic_clear_closes_only_ballistic(ctx):
    # Real feed example: "Відбій балістичної загрози з Криму" is TYPE-SCOPED and
    # KEPT as a spotter signal — it closes ballistic tracks only, leaving an
    # unrelated active shahed open. (A full unscoped spotter відбій, by
    # contrast, is now inert — see test_spotter_full_vidbiy_is_inert.)
    s, m, src = ctx
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Балістика на Київ!", matcher=m,
                         when=BASE + timedelta(seconds=30), source_id=src[0].id, message_id=2)
    await ingest_message(s, text="Відбій балістичної загрози з Криму.", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[0].id, message_id=3)
    ballistic = (await s.scalars(
        select(Threat).where(Threat.target_type == "ballistic"))).first()
    shahed = (await s.scalars(
        select(Threat).where(Threat.target_type == "shahed"))).first()
    assert ballistic.closed_at is not None and ballistic.closed_reason == "all_clear"
    assert shahed.closed_at is None


async def test_unscoped_spotter_vidbiy_no_longer_closes(ctx):
    # "Відбій тривоги та загрози від балістики" is an UNSCOPED full clear
    # (clear_scope=None — the siren itself ended). As a spotter message it is
    # now inert; the shahed stays open until an official alert-end / stale close.
    s, m, src = ctx
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(
        s, text="Відбій тривоги та загрози від балістики, стаємо 🟢!", matcher=m,
        when=BASE + timedelta(minutes=1), source_id=src[0].id, message_id=2,
    )
    shahed_t = (await s.scalars(select(Threat))).first()
    assert shahed_t.closed_at is None


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
    from app.domain.tracking import close_stale_tracks
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
    assert len(out1) == 2  # the sighting event + its incident-attach broadcast
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
    assert t.has_conflict  # shahed vs ballistic on the same track


async def test_no_conflict_when_a_corroborating_source_states_no_type(ctx):
    # Real feed example (threat #187): "БПЛА курс на Бориспіль" (shahed)
    # corroborated by "Бориспіль уважно" (no target type stated at all) — the
    # second source isn't DISAGREEING, it just didn't restate the type, so
    # this must NOT be flagged as a source conflict.
    s, m, src = ctx
    await ingest_message(s, text="БПЛА курс на Бориспіль", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Бориспіль уважно", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[1].id, message_id=2)
    t = (await s.scalars(select(Threat))).first()
    await s.refresh(t, ["events"])
    assert not t.has_conflict


async def test_impact_creates_a_closed_terminal_marker(ctx):
    # A localized strike ("влучання ... в Дніпровському районі") becomes its own
    # impact marker: status=impact, closed-on-creation (a hit is terminal), with
    # a visible event — not an active inbound track.
    s, m, src = ctx
    out = await ingest_message(
        s, text="В Дніпровському районі влучання по нежитловій будівлі",
        matcher=m, when=BASE, source_id=src[0].id, message_id=1)
    t = (await s.scalars(select(Threat))).first()
    await s.refresh(t, ["events"])
    assert t.status == "impact" and t.closed_at is not None
    assert len(t.events) == 1
    # Broadcast as an 'event' (feed) plus the incident-attach 'attack' broadcast.
    assert len(out) == 2
    assert out[0].type == "event" and out[0].event is not None
    assert out[1].type == "attack"


async def test_multi_district_impact_splits_into_separate_markers(ctx):
    """A strike naming several districts ("влучання у Дарницькому та
    Святошинському") must become ONE impact marker PER district — a point hit
    each, never a single multi-district threat (which drew a bogus ballistic
    "track" zigzagging between raions, live T244). Each marker keeps one point."""
    s, m, src = ctx
    await ingest_message(
        s, text="Балістичне влучання у Дарницькому районі та у Святошинському районі",
        matcher=m, when=BASE, source_id=src[0].id, message_id=1)
    # A re-report of the SAME Дарницький strike from another source corroborates
    # THAT marker (one strike), not spawn a new one — and never crosses to
    # Святошинський's marker.
    await ingest_message(
        s, text="Ще одне влучання у Дарницькому районі",
        matcher=m, when=BASE + timedelta(minutes=1), source_id=src[1].id, message_id=2)
    impacts = list(await s.scalars(select(Threat).where(Threat.kind == "impact")))
    assert len(impacts) == 2  # Дарницький + Святошинський, not one merged threat
    for t in impacts:
        n_dist = await s.scalar(
            select(func.count(func.distinct(ThreatEvent.district_id)))
            .where(ThreatEvent.threat_id == t.id)
        )
        assert n_dist == 1  # each marker is a single point, no cross-district line


async def test_impact_does_not_absorb_a_later_sighting_over_same_district(ctx):
    # The impact is closed, so a later real sighting over the SAME district must
    # start its own track, not corroborate onto the (terminal) impact marker.
    s, m, src = ctx
    await ingest_message(
        s, text="В Дніпровському районі влучання по нежитловій будівлі",
        matcher=m, when=BASE, source_id=src[0].id, message_id=1)
    await ingest_message(
        s, text="Шахед над Дніпровським районом", matcher=m,
        when=BASE + timedelta(minutes=1), source_id=src[0].id, message_id=2)
    threats = list(await s.scalars(select(Threat).order_by(Threat.id)))
    assert len(threats) == 2
    impact_t, sighting_t = threats
    assert impact_t.status == "impact"
    assert sighting_t.status != "impact" and sighting_t.closed_at is None


async def test_citywide_alert_created_and_corroborated_into_one(ctx):
    # "Ціль на місто!" with no raion raises ONE city-wide alert; a second
    # city-wide callout shortly after corroborates it, not spawns a new one.
    s, m, src = ctx
    await ingest_message(s, text="Балістика!", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Ціль на місто!", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[0].id, message_id=2)
    await ingest_message(s, text="Балістика на Київ", matcher=m,
                         when=BASE + timedelta(minutes=2), source_id=src[1].id, message_id=3)
    city = list(await s.scalars(select(Threat).where(Threat.scope == "city")))
    assert len(city) == 1
    t = city[0]
    await s.refresh(t, ["events"])
    assert t.closed_at is None and len(t.events) == 2
    # Type inherited from "Балістика!" on channel 0 for the bare "Ціль на місто!".
    assert t.target_type == "ballistic"
    assert t.corroboration_count == 2  # two distinct sources


async def test_citywide_alert_closed_by_all_clear(ctx):
    s, m, src = ctx
    await ingest_alert_message(s, text="‼️У Києві оголошена повітряна тривога!",
                               when=BASE, message_id=100)
    await ingest_message(s, text="Ціль на місто!", matcher=m,
                         when=BASE + timedelta(seconds=30), source_id=src[0].id, message_id=1)
    await ingest_alert_message(s, text="❕Відбій повітряної тривоги!",
                               when=BASE + timedelta(minutes=3), message_id=101)
    t = (await s.scalars(select(Threat).where(Threat.scope == "city"))).first()
    assert t.closed_at is not None and t.status == "lost"


async def test_citywide_event_uses_the_sentinel_district(ctx):
    # The city-wide event attaches to the non-matchable sentinel district so it
    # has a valid point, and no normal sighting ever lands on that district.
    s, m, src = ctx
    await ingest_message(s, text="Балістика на Київ", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    t = (await s.scalars(select(Threat).where(Threat.scope == "city"))).first()
    await s.refresh(t, ["events"])
    sentinel = (await s.scalars(
        select(District).where(District.name_en == "Kyiv (citywide)"))).first()
    assert sentinel is not None
    assert t.events[0].district_id == sentinel.id


async def test_impact_dedup_same_district_one_marker(ctx):
    # Two sources report ONE strike over the same raion minutes apart — it must
    # be a single impact marker with corroboration 2, not two stacked pins.
    s, m, src = ctx
    await ingest_message(
        s, text="У Дніпровському районі фіксуємо пошкоджено будівлю", matcher=m,
        when=BASE, source_id=src[0].id, message_id=1)
    await ingest_message(
        s, text="В Дніпровському районі влучання по нежитловій будівлі", matcher=m,
        when=BASE + timedelta(minutes=2), source_id=src[1].id, message_id=2)
    impacts = list(await s.scalars(select(Threat).where(Threat.status == "impact")))
    assert len(impacts) == 1
    t = impacts[0]
    await s.refresh(t, ["events"])
    assert len(t.events) == 2
    assert t.corroboration_count == 2


async def test_impact_dedup_does_not_merge_different_districts(ctx):
    s, m, src = ctx
    await ingest_message(
        s, text="У Дніпровському районі пошкоджено будівлю", matcher=m,
        when=BASE, source_id=src[0].id, message_id=1)
    await ingest_message(
        s, text="У Святошинському районі пошкоджено будівлю", matcher=m,
        when=BASE + timedelta(minutes=2), source_id=src[0].id, message_id=2)
    impacts = list(await s.scalars(select(Threat).where(Threat.status == "impact")))
    assert len(impacts) == 2


async def test_threats_of_one_attack_share_one_incident(ctx):
    # A ballistic salvo: several tracks + an impact within the window all belong
    # to ONE incident, labelled by the most severe type.
    s, m, src = ctx
    await ingest_message(s, text="Балістика!", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Троя", matcher=m, when=BASE + timedelta(minutes=1),
                         source_id=src[0].id, message_id=2)
    await ingest_message(s, text="Вишневе", matcher=m, when=BASE + timedelta(minutes=2),
                         source_id=src[0].id, message_id=3)
    await ingest_message(s, text="У Дніпровському районі пошкоджено будівлю", matcher=m,
                         when=BASE + timedelta(minutes=4), source_id=src[0].id, message_id=4)
    incs = list(await s.scalars(select(Incident)))
    assert len(incs) == 1
    assert incs[0].target_type == "ballistic"
    tracks = list(await s.scalars(select(Threat)))
    assert all(t.incident_id == incs[0].id for t in tracks)


async def test_full_all_clear_ends_the_incident(ctx):
    s, m, src = ctx
    await ingest_alert_message(s, text="‼️У Києві оголошена повітряна тривога!",
                               when=BASE, message_id=100)
    await ingest_message(s, text="Шахед над Оболонню", matcher=m,
                         when=BASE + timedelta(seconds=30), source_id=src[0].id, message_id=1)
    await ingest_alert_message(s, text="❕Відбій повітряної тривоги!",
                               when=BASE + timedelta(minutes=5), message_id=101)
    inc = (await s.scalars(select(Incident))).first()
    assert inc.ended_at is not None


async def test_attacks_far_apart_are_separate_incidents(ctx):
    s, m, src = ctx
    await ingest_message(s, text="Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    # Two hours later, well past incident_gap — a new attack, new incident.
    await ingest_message(s, text="Шахед над Троєщиною", matcher=m,
                         when=BASE + timedelta(hours=2), source_id=src[0].id, message_id=2)
    incs = list(await s.scalars(select(Incident)))
    assert len(incs) == 2


async def test_ballistic_and_generic_missile_are_not_a_conflict(ctx):
    # The real 04:05/04:06 pair: "8 балістичних ракет С-400" (ballistic) and
    # "до 8 ракет" (generic missile) describe ONE salvo — same missile family,
    # NOT a source conflict. The track should also read as ballistic (specific).
    s, m, src = ctx
    await ingest_message(s, text="Балістика на Київ", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="По Києву пустили до 8 ракет", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[1].id, message_id=2)
    t = (await s.scalars(select(Threat).where(Threat.scope == "city"))).first()
    await s.refresh(t, ["events"])
    assert not t.has_conflict
    assert t.target_type == "ballistic"  # generic missile upgraded to the specific type


async def test_shahed_vs_missile_is_still_a_real_conflict(ctx):
    # A genuine cross-family disagreement must STILL flag a conflict.
    s, m, src = ctx
    await ingest_message(s, text="🔴 Шахед над Осокорками", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Балістика, Осокорки!", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[1].id, message_id=2)
    t = (await s.scalars(select(Threat))).first()
    await s.refresh(t, ["events"])
    assert t.has_conflict


async def test_pulse_corroborates_active_city_alert(ctx):
    # During an open city-wide alert, a terse "Ще вихід"/"3 ракети" callout joins
    # it and bumps the stated count — the salvo coming in.
    s, m, src = ctx
    await ingest_message(s, text="Балістика на Київ", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Ще вихід", matcher=m, when=BASE + timedelta(minutes=1),
                         source_id=src[0].id, message_id=2)
    await ingest_message(s, text="3 ракети", matcher=m, when=BASE + timedelta(minutes=2),
                         source_id=src[1].id, message_id=3)
    city = list(await s.scalars(select(Threat).where(Threat.scope == "city")))
    assert len(city) == 1
    t = city[0]
    await s.refresh(t, ["events"])
    assert len(t.events) == 3          # alert + 2 pulses
    assert t.target_count == 3         # bumped by "3 ракети"
    assert t.target_type == "ballistic"


async def test_pulse_without_active_city_alert_is_ignored(ctx):
    # A lone terse pulse with no open city alert stays suppressed (too terse to
    # localize) — it must NOT create a track.
    s, m, src = ctx
    await ingest_message(s, text="Ціль!", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    assert await _count_threats(s) == 0


async def test_summary_message_becomes_a_feed_notice(ctx):
    # A retrospective recap raises no map threat but IS surfaced as a notice.
    s, m, src = ctx
    out = await ingest_message(
        s, text="Загалом по Києву пустили до 8 балістичних ракет С-400", matcher=m,
        when=BASE, source_id=src[0].id, message_id=1)
    assert await _count_threats(s) == 0
    assert len(out) == 1 and out[0].type == "notice"
    assert out[0].notice.kind == "summary"

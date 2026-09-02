"""The /raw debug serialization (api/raw_query.py::serialize_raw_rows).

Everything here exists to make a feed dump readable without a DB session: WHY a
message produced nothing, WHERE its events landed, and WHEN it was actually
stored. Reviewing a 100-message export on 2026-08-02 stalled on all three.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.raw_query import apply_raw_filters, serialize_raw_rows
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


async def test_the_diagnosis_sees_only_what_the_channels_binding_allows(session):
    """The debug view must diagnose with the matcher the PIPELINE used.

    `for_region` merely PREFERS a region where the feeds restrict to the
    channel's binding, so the view could match a place ingest never saw and then
    explain the row by a filter that needs a district: it read this message from
    a Kyiv-bound channel as `siren_only` where the pipeline had matched nothing
    and dropped it as `not_threat`. 183 corpus rows disagreed that way.
    """
    session.add(District(name_uk="Славутич", name_en="Slavutych", lat=51.5, lon=30.7,
                         region="chernihiv"))
    kyiv_channel = Source(name="Київ", channel_key="kb", role="spotter", region="kyiv")
    session.add(kyiv_channel)
    await session.commit()
    raw = await _raw(session, kyiv_channel, "Тривога надовго, ще 6 сунуть з Славутича",
                     message_id=1)

    out = (await _serialize(session, [raw]))[raw.id]
    assert out.parsed is not None and not out.parsed.matched
    assert out.parsed.district_names == []
    assert out.suppressed_by != "siren_only"


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


async def test_event_chip_carries_both_the_event_and_the_track_type(session):
    """`target_type` is what THIS message was read as; `threat_target_type` is
    what the track now says. They diverge the moment anything corrects the
    track — the context tiers, a later message, an operator — and the admin view
    needs both: one is the audit trail, the other is what the map draws."""
    src = await _spotter(session)
    raw = await _raw(session, src, "Оболонь", message_id=41)
    district = (await session.scalars(select(District))).one()
    threat = Threat(target_type="ballistic", status="tracking")
    session.add(threat)
    await session.commit()
    session.add(ThreatEvent(
        threat_id=threat.id, district_id=district.id, raw_text="Оболонь",
        source_id=src.id, source_message_id=41, event_target_type="unknown",
    ))
    await session.commit()

    chip = (await _serialize(session, [raw]))[raw.id].events[0]
    assert chip.target_type == "unknown"
    assert chip.threat_target_type == "ballistic"


# --- the region filter (apply_raw_filters(regions=[...])) ---
#
# Its semantics are the non-obvious part: a raw message has no region column,
# so "which region is this message about" has to be answered the way ingest
# answered it — by what the message produced, falling back to the channel.

async def _matching(session, *regions: str) -> set[int]:
    stmt = apply_raw_filters(select(RawMessage), regions=list(regions))
    return {r.id for r in await session.scalars(stmt)}


async def _landed(session, src, raw, region: str) -> None:
    """Give a raw message a sighting in `region`, the way ingest would."""
    threat = Threat(target_type="shahed", status="tracking", region=region)
    session.add(threat)
    await session.commit()
    session.add(ThreatEvent(threat_id=threat.id, source_id=src.id,
                            source_message_id=raw.message_id, district_id=1,
                            event_time=raw.event_time))
    await session.commit()


async def test_a_message_is_filed_where_it_landed_not_where_it_came_from(session):
    """The case the filter exists for: a Kyiv channel narrating the northern
    approach. Filing it by channel would bury those messages under Kyiv — and
    they are the 68 stored events over Chernihiv raions that `extra_regions`
    exists to keep."""
    kyiv_channel = Source(name="Київ", channel_key="k", role="spotter", region="kyiv")
    session.add(kyiv_channel)
    await session.commit()

    north = await _raw(session, kyiv_channel, "БпЛА над Ніжином", message_id=1)
    await _landed(session, kyiv_channel, north, "chernihiv")

    assert north.id in await _matching(session, "chernihiv")
    assert north.id not in await _matching(session, "kyiv")


async def test_a_suppressed_message_falls_back_to_its_channels_region(session):
    """Half of what this page is for. A message the parser dropped has no
    district, no track and so no region of its own — but "what did we miss over
    Сумщина last night" is exactly a question about those rows."""
    sumy_channel = Source(name="Суми", channel_key="s", role="spotter", region="sumy")
    session.add(sumy_channel)
    await session.commit()
    dropped = await _raw(session, sumy_channel, "Ціль!", message_id=1)

    assert dropped.id in await _matching(session, "sumy")
    assert dropped.id not in await _matching(session, "kyiv")


async def test_a_landed_message_does_not_also_match_its_channels_region(session):
    """The fallback is a fallback, not an addition: once a message HAS a
    region, the channel's own says nothing extra about it."""
    kyiv_channel = Source(name="Київ", channel_key="k2", role="spotter", region="kyiv")
    session.add(kyiv_channel)
    await session.commit()
    local = await _raw(session, kyiv_channel, "Шахед над Оболонню", message_id=1)
    await _landed(session, kyiv_channel, local, "kyiv")

    assert await _matching(session, "kyiv") == {local.id}
    assert await _matching(session, "chernihiv") == set()


async def test_a_cross_border_message_matches_both_regions(session):
    """One message can legitimately name places on both sides of a border, and
    each sighting is real — so it belongs in both filters, not in a winner."""
    src = await _spotter(session)
    crossing = await _raw(session, src, "Козелець → Вишгород", message_id=1)
    await _landed(session, src, crossing, "chernihiv")
    await _landed(session, src, crossing, "kyiv")

    assert crossing.id in await _matching(session, "chernihiv")
    assert crossing.id in await _matching(session, "kyiv")


# --- multi-select: several regions / several sources at once ---


async def test_several_regions_are_a_union(session):
    """Members of one filter OR together — «Сумщина + Чернігівщина» is one
    question about the northern approach, not two pages to read in turn."""
    sumy = Source(name="Суми", channel_key="ms", role="spotter", region="sumy")
    chern = Source(name="Чернігів", channel_key="mc", role="spotter", region="chernihiv")
    kyiv = Source(name="Київ", channel_key="mk", role="spotter", region="kyiv")
    session.add_all([sumy, chern, kyiv])
    await session.commit()
    s_msg = await _raw(session, sumy, "Ціль!", message_id=1)
    c_msg = await _raw(session, chern, "Ціль!", message_id=2)
    k_msg = await _raw(session, kyiv, "Ціль!", message_id=3)

    assert await _matching(session, "sumy", "chernihiv") == {s_msg.id, c_msg.id}
    assert k_msg.id in await _matching(session, "kyiv", "sumy")


async def test_no_regions_selected_means_no_restriction(session):
    """The empty set is "all", not "none" — the filter's own off position."""
    src = await _spotter(session)
    raw = await _raw(session, src, "Ціль!", message_id=1)
    assert await _matching(session) == {raw.id}


async def test_sources_and_regions_narrow_each_other(session):
    """The two sets AND: «ці джерела над цими областями». A source's message
    that landed elsewhere drops out, and so does another source's message in the
    chosen region."""
    kyiv = Source(name="Київ", channel_key="ak", role="spotter", region="kyiv")
    north = Source(name="Північ", channel_key="an", role="spotter", region="chernihiv")
    session.add_all([kyiv, north])
    await session.commit()
    kyiv_here = await _raw(session, kyiv, "Шахед над Оболонню", message_id=1)
    await _landed(session, kyiv, kyiv_here, "kyiv")
    kyiv_north = await _raw(session, kyiv, "БпЛА над Ніжином", message_id=2)
    await _landed(session, kyiv, kyiv_north, "chernihiv")
    north_msg = await _raw(session, north, "Ціль!", message_id=3)

    stmt = apply_raw_filters(select(RawMessage), source_ids=[kyiv.id], regions=["chernihiv"])
    matched = {r.id for r in await session.scalars(stmt)}
    # Only the Kyiv channel's NORTHERN message: its own local one fails the
    # region half, and the northern channel's fails the source half even though
    # it matches the region.
    assert matched == {kyiv_north.id}
    assert kyiv_here.id not in matched and north_msg.id not in matched


async def test_several_sources_are_a_union(session):
    a = Source(name="A", channel_key="ua", role="spotter")
    b = Source(name="B", channel_key="ub", role="spotter")
    c = Source(name="C", channel_key="uc", role="spotter")
    session.add_all([a, b, c])
    await session.commit()
    a_msg = await _raw(session, a, "Ціль!", message_id=1)
    b_msg = await _raw(session, b, "Ціль!", message_id=2)
    await _raw(session, c, "Ціль!", message_id=3)

    stmt = apply_raw_filters(select(RawMessage), source_ids=[a.id, b.id])
    assert {r.id for r in await session.scalars(stmt)} == {a_msg.id, b_msg.id}

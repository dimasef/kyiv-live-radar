"""Region isolation: two watched regions, two separate track pools.

Kyiv was the only region by assumption, not by configuration — every lookup in
domain/tracking.py scanned all open tracks. These tests pin the boundary that
makes a second region safe to add: a northern sighting must never corroborate,
continue or close a Kyiv track, and none of the Kyiv-only layers (incidents, the
attack banner, the journal) may count it. The one thing that MUST cross is the
target itself: a track reported over the north and then over Kyiv is one track,
and from that moment a Kyiv one.

Ніжин is added as an explicit fixture row rather than relied on from the
gazetteer, so these tests keep pinning the ISOLATION rules even if the northern
gazetteer is later reshuffled.
"""

from datetime import UTC, datetime, timedelta

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base, get_session
from app.gazetteer import DISTRICTS, SOURCES
from app.main import app
from app.models import District, Incident, Source, Threat
from app.parsing import DistrictMatcher, normalize
from app.pipeline.ingest import ingest_alert_message, ingest_message

BASE = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)

# A Chernihiv-oblast town far enough from every Kyiv stem to match cleanly.
NIZHYN = {"name_uk": "Ніжин", "name_en": "Nizhyn", "lat": 51.048, "lon": 31.886}


@pytest_asyncio.fixture
async def ctx(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'r.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        s.add_all(District(name_uk=d["name_uk"], name_en=d["name_en"], lat=d["lat"],
                           lon=d["lon"], aliases=d.get("aliases", []),
                           region=d.get("region", "kyiv")) for d in DISTRICTS)
        s.add(District(**NIZHYN, aliases=[], region="chernihiv"))
        s.add_all(Source(channel_key=x["channel_key"], name=x["name"],
                         trust_weight=x["trust_weight"]) for x in SOURCES)
        s.add(Source(channel_key="north_watch", name="Північ", region="chernihiv"))
        await s.commit()
        matcher = DistrictMatcher(list(await s.scalars(select(District))))
        sources = list(await s.scalars(select(Source)))
        async def _override():
            yield s

        app.dependency_overrides[get_session] = _override
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield s, matcher, sources, client
        app.dependency_overrides.clear()
    await engine.dispose()


async def _tracks(s) -> list[Threat]:
    return list(await s.scalars(select(Threat).order_by(Threat.id)))


def test_a_homonym_resolves_to_the_reporting_channels_side_of_the_border():
    """«Лебедівка», «Рокитне» and «Дніпровське» each name a village in BOTH
    oblasts and the text never says which. The only evidence is who reported
    it, so the matcher takes the channel's region as the tie-break — without
    it, a northern callout lands on a Kyiv village ~60 km away."""
    districts = [{"id": i + 1, **d} for i, d in enumerate(DISTRICTS)]
    kyiv = DistrictMatcher(districts, prefer_region="kyiv")
    north = DistrictMatcher(districts, prefer_region="chernihiv")

    def where(matcher, text):
        hit = matcher.find(normalize(text))[0]
        return next(d for d in districts if d["id"] == hit.district_id)

    for text in ("Лебедівка на гончарівське", "Рокитне", "Дніпровське на сорокошичі"):
        assert where(kyiv, text).get("region", "kyiv") == "kyiv", text
        assert where(north, text)["region"] == "chernihiv", text


def test_region_preference_never_beats_a_more_specific_name():
    """The tie-break is only a tie-break: an entry that explains more of the
    word still wins, whatever region asked."""
    districts = [{"id": i + 1, **d} for i, d in enumerate(DISTRICTS)]
    kyiv = DistrictMatcher(districts, prefer_region="kyiv")
    assert [h.name for h in kyiv.find(normalize("Морівськ на Остер"))] == ["Морівськ", "Остер"]


async def test_northern_sighting_starts_its_own_track(ctx):
    """The same target type over Ніжин and over Оболонь minutes apart are two
    different targets in two different pools — never one corroborated track."""
    s, m, src, _ = ctx
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Шахед на Ніжин", matcher=m,
                         when=BASE + timedelta(minutes=1), source_id=src[0].id, message_id=2)
    tracks = await _tracks(s)
    assert [t.region for t in tracks] == ["kyiv", "chernihiv"]


async def test_northern_kill_report_does_not_close_a_kyiv_track(ctx):
    """The sharpest edge: a reply-less «Збито» names no district, so
    find_open_track falls back to "the newest open track". Unscoped, a northern
    channel's kill report would close whatever Kyiv track happened to be newest
    — a live target silently erased from the map."""
    s, m, src, _ = ctx
    north = next(x for x in src if x.channel_key == "north_watch")
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Збито ціль", matcher=m, when=BASE + timedelta(minutes=2),
                         source_id=north.id, message_id=2)
    tracks = await _tracks(s)
    assert len(tracks) == 1
    assert tracks[0].region == "kyiv" and tracks[0].closed_at is None


async def test_northern_sightings_corroborate_each_other(ctx):
    """Isolation is per-region, not per-track: two reports over the same
    northern district still merge, exactly as they would in Kyiv."""
    s, m, src, _ = ctx
    await ingest_message(s, text="Шахед на Ніжин", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Шахед Ніжин", matcher=m, when=BASE + timedelta(minutes=2),
                         source_id=src[1].id, message_id=2)
    tracks = await _tracks(s)
    assert len(tracks) == 1 and tracks[0].region == "chernihiv"


async def test_official_city_all_clear_leaves_the_northern_track_open(ctx):
    """The Kyiv siren speaks for Kyiv. A northern target is still in the air
    when the city's відбій lands — closing it would erase the early warning."""
    s, m, src, _ = ctx
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Шахед на Ніжин", matcher=m, when=BASE + timedelta(minutes=1),
                         source_id=src[0].id, message_id=2)
    await ingest_alert_message(s, text="‼️УВАГА! У Києві оголошена повітряна тривога!",
                               when=BASE + timedelta(minutes=2), message_id=10)
    await ingest_alert_message(s, text="Відбій повітряної тривоги в Києві",
                               when=BASE + timedelta(minutes=3), message_id=11)
    by_region = {t.region: t for t in await _tracks(s)}
    assert by_region["kyiv"].closed_reason == "all_clear"
    assert by_region["chernihiv"].closed_at is None


async def test_district_less_stand_down_closes_only_its_channels_region(ctx):
    """A «Чисто!» names no place, so it acts on the region of the channel that
    posted it — that is the whole reason sources carry a region."""
    s, m, src, _ = ctx
    north = next(x for x in src if x.channel_key == "north_watch")
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Шахед на Ніжин", matcher=m, when=BASE + timedelta(minutes=1),
                         source_id=north.id, message_id=2)
    await ingest_message(s, text="Чисто!", matcher=m, when=BASE + timedelta(minutes=2),
                         source_id=north.id, message_id=3)
    by_region = {t.region: t for t in await _tracks(s)}
    assert by_region["chernihiv"].closed_reason == "stand_down"
    assert by_region["kyiv"].closed_at is None


async def test_track_crossing_the_border_becomes_one_kyiv_track(ctx):
    """The hand-over the northern watch exists for: one drone called in over
    Ніжин and then over Вишгород stays ONE track and moves into the Kyiv pool,
    where it starts counting as a real target."""
    s, m, src, _ = ctx
    await ingest_message(s, text="Шахед на Ніжин", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Шахед Вишгород", matcher=m, when=BASE + timedelta(minutes=2),
                         source_id=src[0].id, message_id=2, reply_to_message_id=1)
    tracks = await _tracks(s)
    assert len(tracks) == 1
    assert tracks[0].region == "kyiv"


async def test_northern_track_opens_no_attack(ctx):
    """An incident is a Kyiv attack — banner, raion highlight, journal count.
    An early-warning blip 130 km away must not raise one."""
    s, m, src, _ = ctx
    await ingest_message(s, text="Шахед на Ніжин", matcher=m, when=BASE,
                         source_id=src[0].id, message_id=1)
    assert await s.scalar(select(func.count()).select_from(Incident)) == 0


async def test_journal_counts_only_kyiv(ctx):
    """The journal is a record of nights THIS city lived through."""
    s, m, src, client = ctx
    today = datetime.now(UTC).replace(tzinfo=None)
    await ingest_message(s, text="🔴 Шахед над Оболонню", matcher=m, when=today,
                         source_id=src[0].id, message_id=1)
    await ingest_message(s, text="Шахед на Ніжин", matcher=m, when=today + timedelta(minutes=1),
                         source_id=src[0].id, message_id=2)
    day = (await client.get("/journal/days")).json()["days"][-1]
    assert day["target_count"] == 1
    assert day["district_count"] == 1

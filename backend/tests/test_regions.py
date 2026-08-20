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


def test_dymerka_resolves_to_each_channels_own_village():
    """«Димерка» names a village on BOTH sides of the border, and the corpus is
    lopsided: 20 real messages say it, all from Kyiv channels pairing it with
    Бровари («Димерка/Бровари 🔴») — i.e. Велика Димерка — while the northern
    channel's single «Димерка на Козелець» means the Chernihiv one. Before both
    entries existed every one of them resolved to Димер, 47 km away on the far
    side of Kyiv, because "димер" was the only stem that matched. Adding only
    the northern village would have hijacked all 20."""
    districts = [{"id": i + 1, **d} for i, d in enumerate(DISTRICTS)]
    kyiv = DistrictMatcher(districts, prefer_region="kyiv")
    north = DistrictMatcher(districts, prefer_region="chernihiv")

    def names(matcher, text):
        return [h.name for h in matcher.find(normalize(text))]

    assert names(kyiv, "Димерка/Бровари 🔴.") == ["Велика Димерка", "Бровари"]
    assert names(kyiv, "Третій в район Димерки 🔴.") == ["Велика Димерка"]
    assert names(north, "Димерка на Козелець") == ["Димерка", "Козелець"]
    # The plain village keeps its own name to itself.
    assert names(kyiv, "Димер під ударом") == ["Димер"]


def test_northern_toponyms_are_not_captured_by_kyiv_oblast_stems():
    """Each of these drew a target on the edge of Kyiv from a report 100+ km
    north, because the northern place had no entry and a Kyiv-oblast stem
    explained part of the word (08-20 gap analysis)."""
    districts = [{"id": i + 1, **d} for i, d in enumerate(DISTRICTS)]
    kyiv = DistrictMatcher(districts, prefer_region="kyiv")
    north = DistrictMatcher(districts, prefer_region="chernihiv")

    def names(matcher, text):
        return [h.name for h in matcher.find(normalize(text))]

    # Specificity settles this one: "пирогівц" explains more than "пирог". The
    # alias carries the і↔о alternation the stemmer cannot bridge.
    assert names(north, "Пирогівці є") == ["Пирогівці"]
    assert names(north, "Є пироговці") == ["Пирогівці"]
    # ...and the Kyiv museum still answers to its own name.
    assert names(kyiv, "Наступний в район Пирогова") == ["Пирогів"]
    # Обухове ties with Обухів's "обухова" alias, so the channel's region
    # decides — and 16 real «Район Обухова» messages depend on it deciding right.
    assert names(north, "Понори на Обухове") == ["Понори", "Обухове"]
    assert names(kyiv, "Район Обухова 🔴.") == ["Обухів"]
    # Plain coverage gaps: these matched nothing at all.
    assert names(north, "БпЛА біля Рогівки") == ["Рогівка"]
    assert names(north, "Від Леньків на Форостовичі") == ["Леньків", "Форостовичі"]
    # Понорниця exists BECAUSE Понори does — "понор" is a prefix of it.
    assert names(north, "На понорницю") == ["Понорниця"]
    assert names(north, "Понорниця на Корюківку") == ["Понорниця", "Корюківка"]


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


async def test_a_gazetteer_gap_no_longer_breaks_the_reply_chain(ctx):
    """The real 08-20 15:30 sequence, end to end.

    «БпЛА біля Рогівки» matched no district, so it produced no event — and that
    silently cost the two messages after it. Its reply, «На Новгород-сіверський»,
    had no parent event to join, so it opened a track of its own and took its
    type from the channel's last typed message instead: a jet drone over
    Сеньківка, 103 km away and a different target.

    With Рогівка in the gazetteer the chain resolves: ONE track carrying both
    positions (so the map can draw the vector), typed from its own parent. The
    unrelated Сеньківка callout stays its own track — and now counts the "Ще
    два" it always stated.
    """
    s, m, src, _ = ctx
    north = DistrictMatcher(list(await s.scalars(select(District))), prefer_region="chernihiv")
    north_src = next(x for x in src if x.channel_key == "north_watch")
    await ingest_message(s, text="БпЛА біля Рогівки", matcher=north, when=BASE,
                         source_id=north_src.id, message_id=65185)
    await ingest_message(s, text="Ще два реактивні чмошника на Сеньківку", matcher=north,
                         when=BASE + timedelta(seconds=35),
                         source_id=north_src.id, message_id=65186)
    await ingest_message(s, text="На Новгород-сіверський", matcher=north,
                         when=BASE + timedelta(seconds=236),
                         source_id=north_src.id, message_id=65187,
                         reply_to_message_id=65185)

    tracks = await _tracks(s)
    assert len(tracks) == 2
    chain, senkivka = tracks
    await s.refresh(chain, ["events"])
    await s.refresh(senkivka, ["events"])

    names = {d.id: d.name_uk for d in await s.scalars(select(District))}
    assert [names[e.district_id] for e in chain.events] == ["Рогівка", "Новгород-Сіверський"]
    assert chain.target_type == "shahed"      # its own parent's, not Сеньківка's
    assert senkivka.target_type == "jet_drone"
    assert senkivka.target_count == 2         # "Ще два", spelled out

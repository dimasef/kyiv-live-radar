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
from tests.conftest import district_rows

BASE = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)

# A Chernihiv-oblast town far enough from every Kyiv stem to match cleanly.
NIZHYN = {"name_uk": "Ніжин", "name_en": "Nizhyn", "lat": 51.048, "lon": 31.886,
          "region": "chernihiv"}


@pytest_asyncio.fixture
async def ctx(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'r.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        s.add_all(district_rows(NIZHYN))
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
    # Same prefix trap, 08-21: "березан" (Київська Березань) ate «Березанка»,
    # "десн" (смт Десна) ate «Деснянка». Both are Chernihiv-city ring villages,
    # and the first one put a northern target in the KYIV pool — see below.
    assert names(north, "Березанка") == ["Березанка"]
    assert names(north, "Деснянка на понорницю") == ["Деснянка", "Понорниця"]
    # Neither word is a case form of the entry that used to swallow it, so a
    # Kyiv channel typing it means the northern village too.
    assert names(kyiv, "Березанка") == ["Березанка"]
    assert names(kyiv, "Деснянка") == ["Деснянка"]
    # ...and the places they were stolen from still answer to their own names.
    assert names(kyiv, "Баришівка/Березань перші") == ["Баришівка", "Березань"]
    assert names(kyiv, "1 БпЛА на Десну") == ["Десна"]
    assert names(kyiv, "Деснянський район") == ["Деснянський"]


def test_a_northern_village_never_lands_in_the_kyiv_pool():
    """The region leak the prefix traps above cause, stated as its own guard: a
    sighting's pool comes from the DISTRICT's region, so a northern word
    resolving to a Kyiv-oblast entry is not just a wrong dot — it enters the
    Kyiv track pool and shows up for a reader who has the other regions off."""
    districts = [{"id": i + 1, **d} for i, d in enumerate(DISTRICTS)]
    region_of = {d["id"]: d.get("region", "kyiv") for d in districts}
    north = DistrictMatcher(districts, prefer_region="chernihiv")

    for text in ("Березанка", "Деснянка", "Киїнка", "Шестовиця"):
        hits = north.find(normalize(text))
        assert hits, text
        assert all(region_of[h.district_id] == "chernihiv" for h in hits), text


def test_region_preference_never_beats_a_more_specific_name():
    """The tie-break is only a tie-break: an entry that explains more of the
    word still wins, whatever region asked."""
    districts = [{"id": i + 1, **d} for i, d in enumerate(DISTRICTS)]
    kyiv = DistrictMatcher(districts, prefer_region="kyiv")
    assert [h.name for h in kyiv.find(normalize("Морівськ на Остер"))] == ["Морівськ", "Остер"]


def test_a_northern_channel_cannot_reach_a_kyiv_place_at_all():
    """The rule that stops the whole class the traps above patch one by one.

    A prefix trap needs its own gazetteer entry to fix; this needs none — every
    Kyiv-region entry is simply invisible to a northern channel, so a name we
    have never seen cannot leak either. All 10 stored «northern channel -> Kyiv
    district» events were of that shape (2026-08-23 audit)."""
    districts = [{"id": i + 1, **d} for i, d in enumerate(DISTRICTS)]
    region_of = {d["id"]: d.get("region", "kyiv") for d in districts}
    north = DistrictMatcher(districts, prefer_region="chernihiv")

    assert all(region_of[did] == "chernihiv" for did, _ in north.districts_index)
    # The exact words that leaked, including the one that opened a Kyiv attack
    # banner (incident 208): each resolves northern now, or not at all.
    for text in ("Мезин, деснянське", "На Оболоння на короп", "Чайкине на жадове"):
        hits = north.find(normalize(text))
        assert hits, text
        assert all(region_of[h.district_id] == "chernihiv" for h in hits), text
    # A Kyiv place named outright is not reachable either: a northern channel
    # naming a Kyiv microdistrict resolves to nothing and the message lands in
    # the coverage-gap queue, which is visible rather than a phantom Kyiv dot.
    assert north.find(normalize("Троєщина 🔴")) == []
    # And where the stem has a northern counterpart, that is what it resolves to
    # — «Деснянський» never reaches the Kyiv raion. It used to land on Деснянське,
    # a village 126 km from the raion actually being named; both entries now carry
    # the «район»/«р-н» rule that tells them apart (see matcher.MatchContext).
    assert [h.name for h in north.find(normalize("Деснянський район"))] == ["Деснянський район"]
    assert [h.name for h in north.find(normalize("Мезин, деснянське"))] == ["Мезин", "Деснянське"]


def test_the_kyiv_channel_still_watches_the_north():
    """The rule is ASYMMETRIC on purpose: Kyiv channels narrate the northern
    approach (68 stored events over Chernihiv districts) and must keep doing it."""
    districts = [{"id": i + 1, **d} for i, d in enumerate(DISTRICTS)]
    region_of = {d["id"]: d.get("region", "kyiv") for d in districts}
    kyiv = DistrictMatcher(districts, prefer_region="kyiv")

    for text in ("Ніжин", "Козелець", "Славутич"):
        hits = kyiv.find(normalize(text))
        assert hits, text
        assert region_of[hits[0].district_id] == "chernihiv", text


def test_obolonnia_does_not_eat_obolon():
    """The one entry in the 08-23 batch that needed `region_only`: «Оболоння»
    explains MORE of «над Оболонню» than Оболонь does, so the more-specific rule
    would hand six Kyiv callouts to a village 150 km north. prefer_region cannot
    help — that is not a tie. Hidden from the Kyiv matcher, both sides read."""
    districts = [{"id": i + 1, **d} for i, d in enumerate(DISTRICTS)]
    kyiv = DistrictMatcher(districts, prefer_region="kyiv")
    north = DistrictMatcher(districts, prefer_region="chernihiv")

    assert [h.name for h in kyiv.find(normalize("Шахед над Оболонню"))] == ["Оболонь"]
    assert [h.name for h in north.find(normalize("На Оболоння на короп"))] == \
        ["Оболоння", "Короп"]


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


def test_each_city_gets_its_own_station():
    """Both oblasts call their central station «Вокзал», and the J3 batch gave
    only Чернігів an entry — three Kyiv callouts («Вокзал 🔴», «Ще на Вокзал»)
    landed nowhere. Two region_only entries, one word: each channel sees its own.
    """
    districts = [{"id": i + 1, **d} for i, d in enumerate(DISTRICTS)]
    region_of = {d["id"]: d.get("region", "kyiv") for d in districts}
    kyiv = DistrictMatcher(districts, prefer_region="kyiv")
    north = DistrictMatcher(districts, prefer_region="chernihiv")

    k = kyiv.find(normalize("На Вокзал повз Університет 🔴."))
    assert [h.name for h in k] == ["Вокзал"] and region_of[k[0].district_id] == "kyiv"
    n = north.find(normalize("Вокзал-городня"))
    assert [h.name for h in n] == ["Вокзал", "Городня"]
    assert all(region_of[h.district_id] == "chernihiv" for h in n)
    # The station must not steal вул. Вокзальна, which is its own entry.
    assert [h.name for h in kyiv.find(normalize("БПЛА Вокзальна/Чоколівка 🔴."))] == \
        ["Вокзальна площа", "Чоколівка"]


async def test_stated_path_marks_the_track_as_a_real_vector(ctx):
    """«A на B» is one track whose two same-timestamp events are a trajectory.
    The flag is what lets the map draw that leg — without it a whole class of
    northern drone tracks (39 in the live DB on 2026-08-24) rendered as dots."""
    s, m, _sources, _client = ctx
    await ingest_message(s, text="Мамекине на Смяч", matcher=m, when=BASE,
                         source_id=_north_id(_sources), message_id=1)
    track = (await s.scalars(select(Threat))).one()
    await s.refresh(track, ["events"])
    names = {d.id: d.name_uk for d in await s.scalars(select(District))}
    assert [names[e.district_id] for e in track.events] == ["Мамекине", "Смяч"]
    assert track.movement_stated is True
    # One timestamp — precisely the case the map could not previously tell from
    # an enumeration.
    assert len({e.event_time for e in track.events}) == 1


async def test_enumeration_does_not_mark_a_vector(ctx):
    s, m, _sources, _client = ctx
    await ingest_message(s, text="Ніжин, Бахмач увага!", matcher=m, when=BASE,
                         source_id=_north_id(_sources), message_id=2)
    for track in await s.scalars(select(Threat)):
        assert track.movement_stated is False


async def test_a_later_bare_callout_does_not_unset_the_vector(ctx):
    """The flag latches: the leg already drawn stays real."""
    s, m, _sources, _client = ctx
    sid = _north_id(_sources)
    await ingest_message(s, text="Мамекине на Смяч", matcher=m, when=BASE,
                         source_id=sid, message_id=3)
    await ingest_message(s, text="Смяч 🔴", matcher=m, when=BASE + timedelta(minutes=1),
                         source_id=sid, message_id=4)
    track = (await s.scalars(select(Threat))).one()
    assert track.movement_stated is True


def _north_id(sources):
    return next(x for x in sources if x.channel_key == "north_watch").id

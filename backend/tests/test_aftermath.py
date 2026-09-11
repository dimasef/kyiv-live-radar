"""Reading and recording an aftermath message.

Every `text` below is a real message from `app/data/real_sample_messages.jsonl`
(the raw id is in the parametrize label), because this class is defined entirely
by how the channels actually write it. The invariant the whole layer rests on:
`_aftermath` keeps suppressing exactly what it suppresses today, and the raions
it discards are recovered on a separate field.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.domain.aftermath import categorize, read_aftermath
from app.gazetteer import DISTRICTS
from app.models import (
    AFTERMATH_CATEGORIES,
    AftermathReport,
    District,
    Incident,
    Notice,
    Threat,
    utcnow,
)
from app.parsing import DistrictMatcher, normalize, parse_message
from app.pipeline.ingest import ingest_message
from app.realtime.serialize import incident_out


@pytest.fixture(scope="module")
def M() -> DistrictMatcher:
    return DistrictMatcher([{"id": i + 1, **d} for i, d in enumerate(DISTRICTS)])


# --- What a report is about -------------------------------------------------

@pytest.mark.parametrize(
    "raw_id,text,expected",
    [
        (29357, "Поділ.  Горять автомобілі", ["fire"]),
        (29361, "У Подільському районі в багатоповерхівці заблоковані люди.", ["rescue"]),
        (29397, "Дарницький район після нічної атаки  На відео — понівечена "
                "багатоповерхівка, вигорілі авто та наслідки удару", ["damage"]),
        (29403, "Детонації у Вишневому вже немає: із небезпечної зони вже евакуювали "
                "понад 600 людей — речниця ДСНС Київщини", ["rescue"]),
        (29405, "Зараз в Подільському районі рятувальники деблокували тіло загиблого "
                "чоловіка  Разом на цю годину підтверджено 13 загиблих та 56 поранених.",
         ["rescue", "casualties"]),
        (29520, "Двоє постраждалих у Деснянському районі, де ворожий БпЛА впав поруч із "
                "газорозподільною станцією. Обох поранених медики госпіталізували.",
         ["casualties"]),
        (29544, "Жесть! Кадри зараз пожежі на Трої…", ["fire"]),
        (29613, "Тим часом у Вишневому вже 4 день триває ліквідація наслідків після "
                "обстрілу, — ДСНС  На місці працюють понад 300 рятувальників", ["rescue"]),
    ],
)
def test_real_report_is_categorised(raw_id, text, expected):
    reading = read_aftermath(text)
    assert reading is not None, raw_id
    assert reading.categories == expected, raw_id


def test_categories_are_ordered_least_to_most_consequential():
    """`categories[-1]` is what a marker is labelled with, so the order is not
    cosmetic. A rescue in progress outranks the fire and the damage it is
    happening in; the dead outrank all of it."""
    reading = read_aftermath(
        "У Дарницькому районі рятувальники деблокували з-під завалів ще одне тіло, "
        "пожежу ліквідовано, багатоповерхівку зруйновано"
    )
    assert reading is not None
    assert reading.categories == ["damage", "fire", "rescue", "casualties"]


def test_every_category_has_a_severity_rank():
    """The module asserts this at import; the test is what names the failure.
    A category added to the enum without a rank would silently never be read."""
    from app.domain.aftermath import _SEVERITY

    assert set(_SEVERITY) == set(AFTERMATH_CATEGORIES)


def test_a_burning_thing_is_fire_and_a_burnt_thing_is_damage():
    """The one rule that separates the two: is it still happening."""
    assert categorize(normalize("Горять автомобілі")) == ["fire"]
    assert categorize(normalize("вигорілі авто")) == ["damage"]


@pytest.mark.parametrize(
    "text,expected",
    [
        # raw 29567 — the building is what «постраждала», and nothing else in
        # the message is a damage word. Read as casualties it was both mislabelled
        # AND unrecordable (no category at all after the correction).
        ("У Деснянському районі попередньо постраждала багатоповерхівка — КМВА", ["damage"]),
        ("постраждала будівля складу", ["damage"]),
        # Both at once: people AND a structure. Withdrawing casualties here
        # would understate the message, so the correction only applies when
        # «постраждал» was the sole thing carrying it.
        ("Двоє людей постраждали, поранених госпіталізували, постраждала будівля",
         ["damage", "casualties"]),
    ],
)
def test_a_building_can_also_be_harmed(text, expected):
    assert categorize(normalize(text)) == expected


# --- What is not an aftermath at all ---------------------------------------

@pytest.mark.parametrize(
    "raw_id,text",
    [
        # An announced controlled demolition. Reads as rescue work over Вишгород.
        (3998, "Звуки, що чує Вишгород, загрози не становлять. ДСНС попереджали про "
               "знищення вибухонебезпечних предметів."),
        # The rescue service's ordinary peacetime job — six days of an oil spill,
        # which pinned onto Почайна.
        (29439, "Рятувальники вже 6 добу ліквідовують забруднення нафтопродуктами на "
                "Кирилівському озері"),
    ],
)
def test_look_alike_is_not_recorded(raw_id, text):
    assert read_aftermath(text) is None, raw_id


def test_an_aftermath_word_we_cannot_place_records_nothing():
    """`_AFTERMATH` is wider than these four categories (it carries «кмва»,
    «медик», «наслідк»…). A message that fires the suppressor but names no
    category is suppressed as it always was and recorded as nothing — the layer
    never guesses a category it did not read."""
    assert read_aftermath("Про це повідомила КМВА") is None


def test_demolition_wording_does_not_count_as_a_strike_word():
    """«вибухонебезпечних предметів» contains «вибух», so without the veto the
    strike-word gate would wave through the exact class the layer must reject."""
    reading = read_aftermath("Пожежа у Дарницькому районі, працюють піротехніки, "
                             "знайдено вибухонебезпечні предмети")
    assert reading is not None
    assert reading.mentions_strike is False


def test_a_real_strike_report_mentions_a_strike():
    reading = read_aftermath("Дарницький район після нічної атаки — понівечена "
                             "багатоповерхівка")
    assert reading is not None
    assert reading.mentions_strike is True


# --- The raions an aftermath message keeps ---------------------------------

def test_aftermath_keeps_its_raions_on_its_own_field(M):
    """The invariant the layer is built on: `districts` stays empty (every
    predicate downstream depends on a suppressed message reporting nowhere) and
    the raions survive on `aftermath_districts`."""
    r = parse_message(
        "У Подільському районі рятувальники деблокували тіло загиблого чоловіка", M
    )
    assert r.aftermath is True
    assert r.matched is False
    assert r.districts == []
    assert [h.name for h in r.aftermath_districts] == ["Подільський"]


def test_a_normal_sighting_has_no_aftermath_districts(M):
    r = parse_message("🔴 Шахед над Оболонню, курс на Виноградар", M)
    assert r.aftermath is False
    assert r.aftermath_districts == []
    assert [h.name for h in r.districts] == ["Оболонь", "Виноградар"]


def test_an_aftermath_naming_no_place_places_nothing(M):
    """Same rule impacts follow: «є постраждалі» somewhere is not a location."""
    r = parse_message("На жаль, є постраждалі внаслідок атаки", M)
    assert r.aftermath is True
    assert r.aftermath_districts == []


def test_a_standby_raion_is_not_where_something_happened(M):
    """`aftermath_districts` runs through `_drop_standby_districts` like the
    reported set: a raion named only as «готовність» is not the place the fire
    is, which is as true of a fire report as of a sighting."""
    r = parse_message("Пожежа у Дарницькому районі після удару, Оболонь готовність", M)
    names = [h.name for h in r.aftermath_districts]
    assert "Дарницький" in names
    assert "Оболонь" not in names


# --- The write path (Ф2) ----------------------------------------------------
#
# `record_aftermath` runs as a pre-step in `_dispatch`, so these go through the
# real `ingest_message`: what matters is not only that a row appears, but that
# the message's ROUTING is unchanged by it.


@pytest.fixture
def ctx(seeded_session, standard_matcher):
    return seeded_session, standard_matcher


async def _reports(s) -> list[AftermathReport]:
    return list(await s.scalars(select(AftermathReport).order_by(AftermathReport.id)))


async def test_a_strike_report_is_recorded_and_still_suppressed(ctx):
    """Both halves of the invariant in one test: the report exists AND the
    message opened no track — the aftermath layer buys its data without
    loosening a single suppressor."""
    s, matcher = ctx
    await ingest_message(
        s,
        text="Дарницький район після нічної атаки — понівечена багатоповерхівка",
        matcher=matcher, when=utcnow(), source_id=1, message_id=1,
    )
    reports = await _reports(s)
    assert len(reports) == 1
    assert reports[0].categories == ["damage"]
    assert reports[0].region == "kyiv"
    assert reports[0].raw_id is not None and reports[0].source_message_id == 1
    assert await s.scalar(select(func.count()).select_from(Threat)) == 0


async def test_one_report_per_raion(ctx):
    """Same rule impacts follow: a place is where something happened, not a
    waypoint — two raions named is two markers, never one row spanning both."""
    s, matcher = ctx
    await ingest_message(
        s,
        text="Внаслідок атаки сталися пожежі у Деснянському та Святошинському районах",
        matcher=matcher, when=utcnow(), source_id=1, message_id=1,
    )
    reports = await _reports(s)
    names = {
        (await s.get(District, r.district_id)).name_uk for r in reports
    }
    assert names == {"Деснянський", "Святошинський"}
    assert all(r.categories == ["fire"] for r in reports)


async def test_no_strike_word_and_no_live_incident_records_nothing(ctx):
    """«Поділ. Горять автомобілі» on a quiet afternoon could be any car fire.
    Measured: text alone would drop 5 of 18 real reports, which is why the
    incident half of the gate exists — see the next test."""
    s, matcher = ctx
    await ingest_message(
        s, text="Поділ. Горять автомобілі", matcher=matcher, when=utcnow(),
        source_id=1, message_id=1,
    )
    assert await _reports(s) == []


async def test_a_live_incident_vouches_for_a_report_that_names_no_strike(ctx):
    """The same message, during a raid. The open incident is what makes it a
    consequence of that raid rather than an unrelated fire."""
    s, matcher = ctx
    await ingest_message(
        s, text="2х БПЛА Троєщина", matcher=matcher, when=utcnow(),
        source_id=1, message_id=1,
    )
    await ingest_message(
        s, text="Поділ. Горять автомобілі", matcher=matcher, when=utcnow(),
        source_id=1, message_id=2,
    )
    reports = await _reports(s)
    assert len(reports) == 1
    assert reports[0].categories == ["fire"]


async def test_a_look_alike_records_nothing_even_during_a_raid(ctx):
    """The incident half of the gate must not become a blanket permission: an
    announced controlled demolition is not an aftermath at any time."""
    s, matcher = ctx
    await ingest_message(
        s, text="2х БПЛА Троєщина", matcher=matcher, when=utcnow(),
        source_id=1, message_id=1,
    )
    await ingest_message(
        s,
        text="Звуки, що чує Вишгород, загрози не становлять. ДСНС попереджали про "
             "знищення вибухонебезпечних предметів.",
        matcher=matcher, when=utcnow(), source_id=1, message_id=2,
    )
    assert await _reports(s) == []


async def test_a_late_report_is_still_recorded(ctx):
    """The age veto stops a stale message OPENING live state. A private record
    of something already over opens nothing — and «наслідки нічної атаки»
    arrives the next morning by nature, so gating it would lose most of the
    layer on every reconnect backfill."""
    s, matcher = ctx
    await ingest_message(
        s,
        text="Дарницький район після нічної атаки — понівечена багатоповерхівка",
        matcher=matcher, when=utcnow() - timedelta(minutes=45),
        source_id=1, message_id=1, enforce_age=True,
    )
    assert len(await _reports(s)) == 1
    assert await s.scalar(select(func.count()).select_from(Threat)) == 0


async def test_a_summary_gets_both_its_card_and_its_markers(ctx):
    """The reason recording is a pre-step and not a `_dispatch` branch. This
    shape is 2 of the 20 measured reports: as a branch placed after `summary` it
    would record nothing, and placed before it would swallow the feed card that
    every ordinary reader can see."""
    s, matcher = ctx
    await ingest_message(
        s,
        text="У Києві двоє людей постраждали під час нічної атаки. Внаслідок удару "
             "сталися пожежі у Деснянському та Святошинському районах столиці.",
        matcher=matcher, when=utcnow(), source_id=1, message_id=1,
    )
    assert len(await _reports(s)) == 2
    assert await s.scalar(select(func.count()).select_from(Notice)) == 1


async def test_re_delivery_does_not_double_the_layer(ctx):
    """There is no dedup window in this table on purpose (the reports are
    distinct facts, not one event in two voices), so the only thing standing
    between a repeated backfill and a doubled layer is ingest's idempotency
    guard on (source_id, message_id). Pin it here."""
    s, matcher = ctx
    for _ in range(2):
        await ingest_message(
            s,
            text="Дарницький район після нічної атаки — понівечена багатоповерхівка",
            matcher=matcher, when=utcnow(), source_id=1, message_id=1,
        )
    assert len(await _reports(s)) == 1


async def test_a_report_never_reaches_the_attack_rollup(ctx):
    """A report is not a member of the attack, and this is what enforces it.

    `incident_out` publishes the raions an attack was SEEN over, and it already
    excludes impacts for exactly this reason (serialize.py::_incident_district_ids
    — a raion known only because something landed there would leak the strike
    location the endpoint withholds). An aftermath report is the same class of
    knowledge, so it must not appear there either — nor inflate `track_count`.
    """
    s, matcher = ctx
    await ingest_message(
        s, text="2х БПЛА Троєщина", matcher=matcher, when=utcnow(),
        source_id=1, message_id=1,
    )
    await ingest_message(
        s,
        text="Пожежа у Дарницькому районі після удару, працюють рятувальники",
        matcher=matcher, when=utcnow(), source_id=1, message_id=2,
    )
    assert len(await _reports(s)) == 1

    inc = await s.scalar(
        select(Incident).options(
            selectinload(Incident.threats).selectinload(Threat.events)
        )
    )
    out = incident_out(inc, sentinel_district_id=None)
    darnytskyi = await s.scalar(select(District).where(District.name_uk == "Дарницький"))
    assert darnytskyi is not None
    assert darnytskyi.id not in out.district_ids
    assert out.track_count == 1

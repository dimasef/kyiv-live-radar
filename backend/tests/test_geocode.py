"""Address search for home placement (app/geocoding.py).

Nothing here may reach the network: `_fetch` is stubbed in every test that
exercises the OSM tier, and the one test that doesn't stub it asserts the
gazetteer tier answers on its own.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app import geocoding
from app.config import settings
from app.main import app


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_geocoder(monkeypatch):
    geocoding.reset_cache()
    # Tests assert the throttle is *applied*, not that they can sit through it.
    monkeypatch.setattr(settings, "geocode_min_interval_s", 0.0)
    yield
    geocoding.reset_cache()


def _osm_row(lat: float, lon: float, **props) -> dict:
    """One Photon feature. `countrycode` defaults to UA — the country filter has
    a test of its own."""
    props.setdefault("countrycode", "UA")
    return {"properties": props, "geometry": {"coordinates": [lon, lat]}}


def stub_osm(monkeypatch, rows: list[dict], calls: list | None = None):
    async def fake_fetch(q, region):
        if calls is not None:
            calls.append((q, region))
        return rows

    monkeypatch.setattr(geocoding, "_fetch", fake_fetch)


# --- Gazetteer tier -------------------------------------------------------


def test_matches_a_district_by_its_prefix():
    hits = geocoding.gazetteer_hits("троєщ")
    assert hits and hits[0].label == "Троєщина"
    assert hits[0].source == "gazetteer"
    assert hits[0].sublabel == "Київщина"


def test_matches_an_alias_the_spotters_use():
    assert any(h.label == "Троєщина" for h in geocoding.gazetteer_hits("троя"))


def test_ignores_a_query_shorter_than_the_floor():
    assert geocoding.gazetteer_hits("тр") == []


def test_never_offers_the_citywide_sentinel_as_a_place():
    """«Київ (citywide)» is a parser construct — offering it would invite the
    reader to put their house on the sentinel's coordinates."""
    assert all("citywide" not in (h.label or "") for h in geocoding.gazetteer_hits("київ"))


def test_puts_the_readers_own_region_first():
    """Both oblasts have a Тростянець; a Sumy reader must not scroll past
    Chernihiv's to reach theirs."""
    hits = geocoding.gazetteer_hits("тростянець", region="sumy")
    assert hits
    assert hits[0].sublabel == "Сумщина"


# --- OSM tier -------------------------------------------------------------


def test_label_is_the_address_and_the_sublabel_is_where_it_sits():
    label, sub = geocoding.osm_label({
        "street": "вулиця Хрещатик", "housenumber": "22",
        "district": "Печерський район", "city": "Київ", "state": "Київська область",
    })
    assert label == "вулиця Хрещатик 22"
    assert sub == "Печерський район, Київ"


def test_label_keeps_a_named_building_in_front_of_its_address():
    """«Ощадбанк» is how the reader recognises the corner they mean."""
    label, _ = geocoding.osm_label({
        "name": "Ощадбанк", "street": "вулиця Хрещатик", "housenumber": "22",
    })
    assert label == "Ощадбанк, вулиця Хрещатик 22"


def test_label_does_not_repeat_itself_in_its_own_context():
    label, sub = geocoding.osm_label({
        "name": "Оболонь", "district": "Оболонь", "city": "Київ",
    })
    assert (label, sub) == ("Оболонь", "Київ")


def test_a_street_with_no_number_is_still_a_place():
    label, sub = geocoding.osm_label({
        "name": "Тираспольська вулиця", "district": "Подільський район", "city": "Київ",
    })
    assert (label, sub) == ("Тираспольська вулиця", "Подільський район, Київ")


@pytest.mark.asyncio
async def test_osm_results_are_cached_per_query(monkeypatch):
    calls: list = []
    stub_osm(monkeypatch, [_osm_row(50.5, 30.2, street="Садова вулиця", housenumber="5")], calls)
    first = await geocoding.osm_hits("Садова 5", "kyiv")
    second = await geocoding.osm_hits("садова 5", "kyiv")
    assert first == second
    assert len(calls) == 1, "a repeated query must not spend a second request"


@pytest.mark.asyncio
async def test_a_different_region_is_a_different_lookup(monkeypatch):
    calls: list = []
    stub_osm(monkeypatch, [], calls)
    await geocoding.osm_hits("Садова 5", "kyiv")
    await geocoding.osm_hits("Садова 5", "sumy")
    assert [c[1] for c in calls] == ["kyiv", "sumy"]


@pytest.mark.asyncio
async def test_an_osm_failure_degrades_to_the_gazetteer(monkeypatch):
    """The search box sits over a map the reader can still pan by hand — a
    geocoder outage must cost results, never the input."""
    async def boom(q, region):
        raise RuntimeError("geocoder down")

    monkeypatch.setattr(geocoding, "_fetch", boom)
    assert await geocoding.osm_hits("Садова 5", "kyiv") == []
    hits = await geocoding.search("троєщ", "kyiv")
    assert hits and hits[0].source == "gazetteer"


@pytest.mark.asyncio
async def test_osm_can_be_switched_off_entirely(monkeypatch):
    calls: list = []
    stub_osm(monkeypatch, [_osm_row(50.5, 30.2, street="Садова вулиця", housenumber="5")], calls)
    monkeypatch.setattr(settings, "geocode_osm_enabled", False)
    assert await geocoding.osm_hits("Садова 5", "kyiv") == []
    assert calls == []


@pytest.mark.asyncio
async def test_one_place_known_to_both_tiers_is_listed_once(monkeypatch):
    stub_osm(monkeypatch, [_osm_row(50.515, 30.600, name="Троєщина", city="Київ")])
    hits = await geocoding.search("троєщ", "kyiv")
    assert [h.source for h in hits] == ["gazetteer"]


@pytest.mark.asyncio
async def test_search_lists_our_own_entries_before_osm(monkeypatch):
    stub_osm(monkeypatch, [_osm_row(50.4, 30.4, name="Троєщинська вулиця", city="Київ")])
    hits = await geocoding.search("троєщ", "kyiv")
    assert [h.source for h in hits] == ["gazetteer", "osm"]


# --- Endpoint -------------------------------------------------------------


@pytest.mark.asyncio
async def test_endpoint_returns_hits(client, monkeypatch):
    stub_osm(monkeypatch, [
        _osm_row(50.54, 30.21, street="Садова вулиця", housenumber="5", city="Буча"),
    ])
    body = (await client.get("/geocode", params={"q": "Садова 5", "region": "kyiv"})).json()
    assert body
    row = body[-1]
    assert row["label"] == "Садова вулиця 5"
    assert (row["lat"], row["lon"]) == (50.54, 30.21)
    assert row["source"] == "osm"


@pytest.mark.asyncio
async def test_endpoint_answers_a_too_short_query_with_nothing(client, monkeypatch):
    calls: list = []
    stub_osm(monkeypatch, [], calls)
    assert (await client.get("/geocode", params={"q": "тр"})).json() == []
    assert calls == [], "a two-letter query must not reach OSM"


@pytest.mark.asyncio
async def test_endpoint_rejects_an_unknown_region(client, monkeypatch):
    stub_osm(monkeypatch, [])
    resp = await client.get("/geocode", params={"q": "Садова", "region": "lviv"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_one_address_held_three_ways_by_osm_is_one_row(monkeypatch):
    """«Хрещатик 22» really answers as a node, a way and a relation — three
    identical lines metres apart."""
    street = {"street": "вулиця Хрещатик", "district": "Центр", "city": "Київ"}
    stub_osm(monkeypatch, [
        _osm_row(50.4498, 30.5231, housenumber="22", **street),
        _osm_row(50.4501, 30.5227, housenumber="22", **street),
        _osm_row(50.4495, 30.5229, housenumber="24", **street),
    ])
    hits = await geocoding.osm_hits("Хрещатик 22", "kyiv")
    # The neighbouring house is metres away and must survive — deduping on
    # distance instead of text would have eaten it.
    assert [h.label for h in hits] == ["вулиця Хрещатик 22", "вулиця Хрещатик 24"]


@pytest.mark.asyncio
async def test_a_result_across_the_border_is_dropped(monkeypatch):
    """The bounding box bleeds over four borders — Чернігівщина's reaches into
    Belarus and Russia — so the country code is the actual filter."""
    stub_osm(monkeypatch, [
        _osm_row(52.1, 31.3, name="Добруш", countrycode="BY"),
        _osm_row(51.5, 31.3, name="Чернігів", countrycode="UA"),
    ])
    hits = await geocoding.osm_hits("чернігів", "chernihiv")
    assert [h.label for h in hits] == ["Чернігів"]

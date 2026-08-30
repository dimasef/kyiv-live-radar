"""The public region catalogue.

The client renders region names, groups sources and draws the oblast layer from
this, so a newly declared region shows up everywhere without a frontend edit.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.regions import REGION_SPECS


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.mark.asyncio
async def test_lists_every_declared_region_home_first(client):
    body = (await client.get("/regions")).json()
    assert [r["id"] for r in body] == [s.id for s in REGION_SPECS]
    assert body[0]["is_home"] is True
    assert sum(r["is_home"] for r in body) == 1


@pytest.mark.asyncio
async def test_reports_which_regions_are_not_covered_yet(client):
    body = {r["id"]: r for r in (await client.get("/regions")).json()}
    assert body["kyiv"]["active"] is True
    assert body["chernihiv"]["active"] is True
    assert body["sumy"]["active"] is True  # activated 2026-08-28
    assert body["sumy"]["name_uk"] == "Сумщина"
    # Дніпропетровщина is still declared-but-empty: the picker has to be able to
    # say «готується» for it.
    assert body["dnipro"]["active"] is False


@pytest.mark.asyncio
async def test_a_localizing_region_reads_as_covered_before_it_is_activated(client):
    """Харківщина has had gazetteer entries (and live tracks) since 2026-08-29
    while `RegionSpec.active` waits out its break-in period. The client asks
    "is there anything to see here", so it must hear yes — the map drew the
    oblast dashed as «поки без даних» over an oblast that was accumulating
    tracks."""
    from app.regions import SPEC_BY_ID

    body = {r["id"]: r for r in (await client.get("/regions")).json()}
    assert SPEC_BY_ID["kharkiv"].active is False
    assert body["kharkiv"]["active"] is True


@pytest.mark.asyncio
async def test_every_region_carries_a_map_centre(client):
    for row in (await client.get("/regions")).json():
        assert 44 < row["center_lat"] < 53
        assert 22 < row["center_lon"] < 41


@pytest.mark.asyncio
async def test_outlines_are_served_even_before_the_data_file_exists(client):
    """The map layer fetches this lazily; a missing file must be an empty layer,
    not a 500 that takes the whole map down with it."""
    r = await client.get("/regions/geometry")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)

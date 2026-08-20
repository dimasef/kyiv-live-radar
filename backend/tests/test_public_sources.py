"""The public «Джерела» list behind the map legend.

The rule that matters is which channels get a LINK: a private channel is one we
were let into, and republishing its invite would hand that access to everyone
looking at the map.
"""
from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.public.sources import public_channel_url
from app.db import Base, get_session
from app.main import app
from app.models import Source


@pytest_asyncio.fixture
async def client(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'t.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        async def _override():
            yield s

        app.dependency_overrides[get_session] = _override
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, s
        app.dependency_overrides.clear()
    await engine.dispose()


def test_only_a_public_username_becomes_a_link():
    assert public_channel_url("kyiv_nebo") == "https://t.me/kyiv_nebo"
    # An invite link is access we were given, not a public page.
    assert public_channel_url("+AbCdEfGhIjK") is None
    assert public_channel_url("t.me/joinchat/AbCd") is None
    # A numeric channel id has nothing to point at.
    assert public_channel_url("-1001234567890") is None
    assert public_channel_url("1234567890") is None
    # Telegram usernames start with a letter and are at least 5 chars.
    assert public_channel_url("_abcde") is None
    assert public_channel_url("abcd") is None


async def test_lists_active_channels_spotters_first(client):
    c, s = client
    s.add_all([
        Source(channel_key="KyivCityOfficial", name="КМДА", role="alert", region="kyiv"),
        Source(channel_key="kyiv_nebo", name="Київське небо", role="spotter", region="kyiv"),
        Source(channel_key="chyste_nebo", name="Чисте Небо", role="spotter",
               region="chernihiv"),
    ])
    await s.commit()

    rows = (await c.get("/sources")).json()
    assert [r["name"] for r in rows] == ["Київське небо", "Чисте Небо", "КМДА"]
    assert rows[0]["url"] == "https://t.me/kyiv_nebo"
    assert rows[2]["role"] == "alert"


async def test_an_archived_channel_is_not_credited(client):
    """We are not standing on it any more — listing it would credit it for data
    it no longer provides."""
    c, s = client
    s.add(Source(channel_key="ppo_kiev", name="ППО", role="spotter", is_active=False))
    await s.commit()
    assert (await c.get("/sources")).json() == []


async def test_a_private_channel_is_named_but_not_linked(client):
    c, s = client
    s.add(Source(channel_key="+SecretInvite1", name="Закритий канал", role="spotter"))
    await s.commit()
    rows = (await c.get("/sources")).json()
    assert rows[0]["name"] == "Закритий канал"
    assert rows[0]["url"] is None


async def test_our_own_channel_is_not_credited_as_a_source(client):
    """It ingests like any other channel, but the block exists to point at the
    volunteer channels the map stands on — crediting ourselves there is a link
    back to the page the reader already has open."""
    c, s = client
    s.add_all([
        Source(channel_key="kyiv_live_radar", name="Kyiv Live Radar", role="spotter"),
        Source(channel_key="kyiv_nebo", name="Київське небо", role="spotter"),
    ])
    await s.commit()
    rows = (await c.get("/sources")).json()
    assert [r["name"] for r in rows] == ["Київське небо"]


async def test_the_public_list_never_carries_trust_weight(client):
    """It is an internal fusion knob; published, it reads as our public rating of
    a volunteer channel."""
    c, s = client
    s.add(Source(channel_key="kyiv_nebo", name="Київське небо", trust_weight=0.3))
    await s.commit()
    rows = (await c.get("/sources")).json()
    assert "trust_weight" not in rows[0]
    assert "channel_key" not in rows[0]

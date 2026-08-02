"""Custom avatar upload (PATCH /auth/me + app/auth/avatar.py).

The stored string is rendered as an <img src> in OTHER users' browsers, so the
validation is the feature — the UI is just a canvas that shrinks a photo.
"""
from __future__ import annotations

import base64

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.avatar import MAX_AVATAR_CHARS, AvatarError, validate_avatar_data_url
from app.config import settings
from app.db import Base, get_session
from app.main import app

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff" + b"\x00" * 32
WEBP = b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 24


def _data_url(mime: str, raw: bytes) -> str:
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "auth_jwt_secret", "avatar-test-secret")
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
            yield c
        app.dependency_overrides.clear()
    await engine.dispose()


async def _auth(c: AsyncClient, email: str = "av@x.com") -> dict:
    r = await c.post("/auth/register", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {r.json()['access']}"}


def test_accepts_the_three_raster_formats():
    for mime, raw in (("image/png", PNG), ("image/jpeg", JPEG), ("image/webp", WEBP)):
        url = _data_url(mime, raw)
        assert validate_avatar_data_url(url) == url


def test_rejects_a_remote_url():
    # The reason this is a hard no: a stored https URL would be fetched by every
    # contact's browser, handing whoever controls it their IPs and a presence
    # signal every time someone opens their contact list.
    with pytest.raises(AvatarError):
        validate_avatar_data_url("https://evil.example/track.png")


def test_rejects_svg_even_though_it_is_an_image():
    with pytest.raises(AvatarError):
        validate_avatar_data_url(_data_url("image/svg+xml", b"<svg/>"))


def test_rejects_bytes_that_contradict_the_declared_type():
    with pytest.raises(AvatarError):
        validate_avatar_data_url(_data_url("image/png", JPEG))
    # RIFF alone isn't WebP — it's also WAV and AVI.
    with pytest.raises(AvatarError):
        validate_avatar_data_url(_data_url("image/webp", b"RIFF" + b"\x00" * 4 + b"WAVE"))


def test_rejects_oversized_and_malformed_payloads():
    with pytest.raises(AvatarError):
        validate_avatar_data_url("data:image/png;base64," + "A" * MAX_AVATAR_CHARS)
    with pytest.raises(AvatarError):
        validate_avatar_data_url("data:image/png;base64,not!valid!base64")
    with pytest.raises(AvatarError):
        validate_avatar_data_url(_data_url("image/png", b""))


async def test_patch_me_sets_and_clears_the_avatar(client):
    headers = await _auth(client)
    url = _data_url("image/webp", WEBP)

    r = await client.patch("/auth/me", json={"avatar_url": url}, headers=headers)
    assert r.status_code == 200 and r.json()["avatar_url"] == url

    # Explicit null removes it — the UI falls back to the monogram.
    r = await client.patch("/auth/me", json={"avatar_url": None}, headers=headers)
    assert r.status_code == 200 and r.json()["avatar_url"] is None


async def test_patch_me_only_touches_the_fields_it_was_given(client):
    headers = await _auth(client, "partial@x.com")
    await client.patch("/auth/me", json={"display_name": "Дмитро"}, headers=headers)
    r = await client.patch(
        "/auth/me", json={"avatar_url": _data_url("image/png", PNG)}, headers=headers
    )
    # Sending only an avatar must not blank the name.
    assert r.json()["display_name"] == "Дмитро"


async def test_patch_me_rejects_a_bad_avatar_with_a_readable_message(client):
    headers = await _auth(client, "bad@x.com")
    r = await client.patch(
        "/auth/me", json={"avatar_url": "https://evil.example/x.png"}, headers=headers
    )
    assert r.status_code == 400 and r.json()["detail"]


async def test_patch_me_requires_auth(client):
    assert (await client.patch("/auth/me", json={"display_name": "x"})).status_code == 401


async def test_display_name_is_capped_and_trimmed(client):
    """25 chars is what fits a contact row and a map tooltip; the server is
    where that's enforced, not just the input's maxLength."""
    headers = await _auth(client, "named@x.com")

    r = await client.patch("/auth/me", json={"display_name": "x" * 26}, headers=headers)
    assert r.status_code == 422

    r = await client.patch("/auth/me", json={"display_name": "  Дмитро  "}, headers=headers)
    assert r.json()["display_name"] == "Дмитро"

    # Blank clears it — the UI then falls back to the email.
    r = await client.patch("/auth/me", json={"display_name": "   "}, headers=headers)
    assert r.json()["display_name"] is None

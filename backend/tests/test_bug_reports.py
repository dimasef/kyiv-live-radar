"""Filing a bug and working the inbox (app/api/public/bugs.py + admin/bugs.py),
driven over ASGITransport like tests/test_gamification.py."""
from __future__ import annotations

import base64

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.public.bugs import RATE_LIMIT_PER_HOUR
from app.auth.security import encode_access
from app.config import settings
from app.db import Base, get_session
from app.main import app
from app.models import BugReport, User

# Smallest thing that survives the magic-byte check in app/images.py.
PNG = "data:image/png;base64," + base64.b64encode(
    b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
).decode()

ANDROID_UA = (
    "Mozilla/5.0 (Linux; Android 14; SM-S911B) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/138.0.7204.63 Mobile Safari/537.36"
)


@pytest_asyncio.fixture
async def env(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "auth_jwt_secret", "bug-test-secret")
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


async def _register(c: AsyncClient, email: str) -> dict:
    r = await c.post("/auth/register", json={"email": email, "password": "password123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access']}"}


async def _admin(session) -> dict:
    user = User(email="admin@x.com", role="admin", password_hash="x")
    session.add(user)
    await session.commit()
    return {"Authorization": f"Bearer {encode_access(user)}"}


def _report(**over) -> dict:
    body = {
        "description": "Мапа поїхала в кут екрана після відкриття налаштувань",
        "context": {
            "app_version": "0.25.5",
            "route": "/",
            "user_agent": ANDROID_UA,
            "viewport_w": 393,
            "viewport_h": 760,
            "dpr": 2.75,
            "scale": 0.25,
            "standalone": False,
            "language": "uk",
            "online": True,
        },
    }
    body.update(over)
    return body


@pytest.mark.asyncio
async def test_filing_a_bug_keeps_the_context_that_makes_it_diagnosable(env):
    c, s = env
    headers = await _register(c, "reporter@x.com")

    r = await c.post("/bug-reports", json=_report(screenshot=PNG), headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "new"

    row = await s.get(BugReport, r.json()["id"])
    # Derived server-side from the UA — the two labels the admin list shows.
    assert row.browser == "Chrome 138"
    assert row.os == "Android 14"
    assert row.app_version == "0.25.5"
    assert row.screenshot == PNG
    # The page scale is the whole diagnosis of the 2026-08-12 report; it must
    # survive into storage, not be flattened into prose.
    assert row.context["scale"] == 0.25
    assert row.context["viewport_w"] == 393
    # Not duplicated into the JSON blob — they have their own columns.
    assert "user_agent" not in row.context


@pytest.mark.asyncio
async def test_anonymous_cannot_file(env):
    c, _ = env
    r = await c.post("/bug-reports", json=_report())
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_a_report_carrying_nothing_is_rejected(env):
    c, _ = env
    headers = await _register(c, "empty@x.com")
    r = await c.post("/bug-reports", json=_report(description="   "), headers=headers)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_a_screenshot_alone_is_a_valid_report(env):
    """A picture of a mangled screen often says more than a sentence about it."""
    c, s = env
    headers = await _register(c, "picture@x.com")
    r = await c.post(
        "/bug-reports", json=_report(description="", screenshot=PNG), headers=headers
    )
    assert r.status_code == 200, r.text
    assert (await s.get(BugReport, r.json()["id"])).screenshot == PNG


@pytest.mark.asyncio
async def test_a_screenshot_that_is_not_an_image_is_rejected(env):
    """The stored string ends up in an <img src> in the admin's browser."""
    c, _ = env
    headers = await _register(c, "evil@x.com")
    svg = "data:image/svg+xml;base64," + base64.b64encode(b"<svg onload=alert(1)>").decode()
    r = await c.post("/bug-reports", json=_report(screenshot=svg), headers=headers)
    assert r.status_code == 400

    lying = "data:image/png;base64," + base64.b64encode(b"not a png at all").decode()
    r = await c.post("/bug-reports", json=_report(screenshot=lying), headers=headers)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_one_account_cannot_flood_the_inbox(env):
    c, _ = env
    headers = await _register(c, "flood@x.com")
    for _ in range(RATE_LIMIT_PER_HOUR):
        assert (await c.post("/bug-reports", json=_report(), headers=headers)).status_code == 200
    r = await c.post("/bug-reports", json=_report(), headers=headers)
    assert r.status_code == 429


@pytest.mark.asyncio
async def test_admin_sees_the_inbox_and_works_a_ticket(env):
    c, s = env
    reporter = await _register(c, "who@x.com")
    filed = await c.post("/bug-reports", json=_report(), headers=reporter)
    report_id = filed.json()["id"]

    admin = await _admin(s)
    r = await c.get("/admin/bug-reports", headers=admin)
    assert r.status_code == 200
    [ticket] = r.json()
    # Who filed it, so a follow-up question is possible at all.
    assert ticket["reporter"]["email"] == "who@x.com"
    assert ticket["browser"] == "Chrome 138"

    r = await c.patch(
        f"/admin/bug-reports/{report_id}", json={"status": "closed"}, headers=admin
    )
    assert r.status_code == 200 and r.json()["status"] == "closed"

    assert (await c.get("/admin/bug-reports?status=new", headers=admin)).json() == []
    assert len((await c.get("/admin/bug-reports?status=closed", headers=admin)).json()) == 1

    assert (await c.delete(f"/admin/bug-reports/{report_id}", headers=admin)).status_code == 200
    assert await s.get(BugReport, report_id) is None


@pytest.mark.asyncio
async def test_the_inbox_is_admin_only(env):
    c, _ = env
    plain = await _register(c, "plain@x.com")
    assert (await c.get("/admin/bug-reports", headers=plain)).status_code == 403
    assert (await c.get("/admin/bug-reports")).status_code == 401


def test_a_deleted_account_leaves_its_bug_behind():
    """Losing the reporter must not lose the report. Asserted on the schema
    rather than by deleting a row: SQLite ignores foreign keys unless the
    pragma is on, so a behavioural test here would pass for the wrong reason
    and prove nothing about Postgres, which is what production runs."""
    [fk] = BugReport.__table__.c.user_id.foreign_keys
    assert fk.ondelete == "SET NULL"
    assert BugReport.__table__.c.user_id.nullable

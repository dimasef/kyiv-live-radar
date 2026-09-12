import asyncio
import os
from functools import lru_cache

# BEFORE app.config is imported (which is what every `import app.*` below does):
# the local .env carries the real Sentry DSN, so a failing test used to ship its
# traceback to the production issue stream and page the maintainer about a bug
# that only ever existed in a test stub. Tests must never talk to Sentry.
os.environ["SENTRY_DSN"] = ""
# Same reasoning, and the same .env, for the Anthropic key — except this one
# costs money. `stub_llm` below claims "real code reads
# settings.anthropic_api_key='' -> never calls the network", which was only ever
# true on CI: locally pydantic-settings loads the maintainer's real key, so any
# test ingesting an untyped localized sighting fired a LIVE type-classifier call.
# It stayed invisible because the 2s timeout usually killed the call before it
# returned — raising that timeout to 3.5s promptly made
# test_untyped_callout_stays_unknown_in_a_combined_incident flaky, which is how
# it surfaced. The fixtures that WANT an LLM monkeypatch the key back to
# "test-key" alongside a stubbed client, so nothing legitimate loses coverage.
os.environ["ANTHROPIC_API_KEY"] = ""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.api.read_cache as read_cache
import app.domain.districts as districts
import app.pipeline.ingest as ingest
import app.pipeline.triage as triage
from app.db import Base, get_session
from app.gazetteer import SOURCES
from app.main import app
from app.models import District, Source
from app.parsing import DistrictMatcher
from app.parsing.rules import LlmUsage


@pytest.fixture(autouse=True)
def _reset_ingest_globals():
    """Reset process-global ingest/tracking caches before every test.

    The type-context globals (per-channel inheritance, classifier declines, the
    feed generation counter) and the cached sentinel district id
    (`domain.districts`) are process-global. Each test builds a
    FRESH DB, so a value cached from a prior test's DB would leak in — a
    spurious inherited type, or the wrong sentinel id. Live processes don't
    hit this (one long-lived DB, real-time progression).

    The triage queue is bound to the event loop it was created on; pytest-asyncio
    builds a fresh loop per test, so a queue from a prior test would raise. Drop
    it (and the cost-guard cache) here too.
    """
    ingest.reset_type_context()
    districts.reset_cache()
    triage.reset_queue()
    triage._invalidate_spend_cache()
    read_cache.clear()
    yield
    ingest.reset_type_context()
    districts.reset_cache()
    triage.reset_queue()
    triage._invalidate_spend_cache()


def make_verdict(*, category="noise", surface=False, summary="", origin_place="none",
                 origin_sector="none", district_ids=None, target_type="unknown",
                 status="sighting", is_new_target=False, confidence=0.8):
    """Build a well-formed LLM triage verdict for tests (mirrors llm._normalize)."""
    return {
        "schema_version": 2, "category": category, "origin_place": origin_place,
        "origin_sector": origin_sector, "surface": surface, "summary": summary,
        "district_ids": district_ids or [], "target_type": target_type,
        "status": status, "is_new_target": is_new_target, "confidence": confidence,
    }


class _StubLlm:
    """Canned-verdict fake for llm_triage / llm_extract, keyed by text substring.
    No network ever. Records calls; supports injected latency for ordering tests."""

    def __init__(self):
        self._rules: list[tuple[str, dict]] = []
        self.default = make_verdict()
        self.latency = 0.0
        self.calls: list[str] = []

    def set(self, substring: str, verdict: dict):
        self._rules.append((substring, verdict))

    def verdict_for(self, text: str) -> dict:
        for sub, v in self._rules:
            if sub in text:
                return v
        return self.default

    async def _triage(self, text, matcher):
        self.calls.append(text)
        if self.latency:
            await asyncio.sleep(self.latency)
        return self.verdict_for(text), LlmUsage(10, 10, 0.0001)


@pytest.fixture
def stub_llm(monkeypatch):
    """Patch the LLM entry points with a canned fake and enable the triage path.

    The suite runs with an empty `anthropic_api_key` (see the env stub at the top
    of this file), which is what keeps every other test off the network; this
    fixture hands the key back ALONGSIDE a stubbed client, so the code under test
    takes its real branch without anything reaching the API."""
    from app.config import settings

    stub = _StubLlm()
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(settings, "triage_enabled", True)
    monkeypatch.setattr("app.parsing.llm.llm_triage", stub._triage)
    return stub


async def drain_triage(stub_run_consumer=None):
    """Run the triage consumer until the queue is empty, then stop it — for
    end-to-end enqueue->route tests."""
    queue = triage.get_queue()
    task = asyncio.create_task(triage.run_triage_consumer())
    try:
        await asyncio.wait_for(queue.join(), timeout=5)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def district_rows(*extra: dict) -> list:
    """Gazetteer -> District rows carrying EVERY column the matcher reads.

    Each fixture used to hand-roll this, and each dropped a different one:
    `region` was missing from most of them, `region_only` from all — so a
    region-exclusive entry like «Оболоння» was visible to every test matcher and
    quietly ate «над Оболонню», which is a failure the production seeder
    (app/seed.py, which does copy both) cannot have. One builder, one place to
    add the next column.

    `extra` are test-local districts (a fixture's own «Ніжин»), appended after
    the gazetteer so they seed with the same defaults.
    """
    from app.gazetteer import DISTRICTS
    from app.models import HOME_REGION

    return [
        District(
            name_uk=d["name_uk"], name_en=d["name_en"], lat=d["lat"], lon=d["lon"],
            aliases=d.get("aliases", []), region=d.get("region", HOME_REGION),
            region_only=bool(d.get("region_only", False)),
        )
        for d in [*DISTRICTS, *extra]
    ]


@pytest.fixture(autouse=True)
def _safe_jwt_secret(monkeypatch):
    """PyJWT's `InsecureKeyLengthWarning` fires under 32 bytes for HS256. Give
    every test a secret that clears it by default; a test that wants its own
    (to assert on a specific token, say) still overrides it afterward — keep
    those overrides >=32 bytes too, or the warning is back."""
    from app.config import settings

    monkeypatch.setattr(settings, "auth_jwt_secret", "default-test-jwt-secret-32-bytes!")


@pytest_asyncio.fixture
async def db_engine():
    """Function-scoped in-memory engine, shared by `session`/`client` below.

    `StaticPool` is load-bearing, not a performance tweak: without it, every
    aiosqlite connection opened against `:memory:` is a SEPARATE empty
    database, so a session that reconnects mid-test would see no tables.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def db_sessionmaker(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(db_sessionmaker):
    async with db_sessionmaker() as s:
        yield s


@pytest_asyncio.fixture
async def client(session):
    """The HTTP client alone. A test that also needs the DB session takes
    `session` directly rather than unpacking a tuple out of this fixture."""

    async def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seeded_session(session):
    """`session` plus the standard gazetteer + source roster, committed —
    what most `ctx`/`db` fixtures used to hand-roll per file."""
    session.add_all(district_rows())
    session.add_all(
        Source(channel_key=x["channel_key"], name=x["name"],
               trust_weight=x.get("trust_weight", 1.0), role=x.get("role", "spotter"))
        for x in SOURCES
    )
    await session.commit()
    return session


@lru_cache(maxsize=1)
def _build_standard_matcher() -> tuple[DistrictMatcher, tuple[int, ...]]:
    """Built once for the whole run, not per test — compiling the ~723-entry
    stem regex set measured at ~119ms, the single biggest per-test setup cost.
    No DB: ids are assigned by hand the way SQLite will (1..N in insertion
    order), and `test_standard_matcher_ids_match_a_fresh_seed` pins that they
    agree with a real seed. `DistrictMatcher.__init__` (parsing/matcher.py)
    only reads id/name/aliases off each row, so transient objects suffice."""
    rows = district_rows()
    for i, d in enumerate(rows, start=1):
        d.id = i
    return DistrictMatcher(rows), tuple(d.id for d in rows)


@pytest.fixture(scope="session")
def standard_matcher() -> DistrictMatcher:
    return _build_standard_matcher()[0]


@pytest.fixture(scope="session")
def standard_district_ids() -> tuple[int, ...]:
    return _build_standard_matcher()[1]

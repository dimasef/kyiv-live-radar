"""Tests for app/alerts.py (idempotent signal application, failsafe closure)
and app/ingest.py::ingest_alert_message (alert-channel messages only ever
create Alert rows — never a Threat or Notice, unlike the spotter pipeline).
"""

from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.domain.alerts import AlertSignal, apply_alert_signal, close_stale_alerts
from app.models import Alert, Notice, RawMessage, Threat
from app.pipeline.ingest import ingest_alert_message

BASE = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'a.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()


async def _count(session, model) -> int:
    return await session.scalar(select(func.count()).select_from(model))


# --- apply_alert_signal idempotency ---

async def test_start_opens_an_alert(session):
    a = await apply_alert_signal(session, AlertSignal(scope="city", action="start", when=BASE))
    assert a is not None
    assert a.scope == "city" and a.ended_at is None


async def test_double_start_is_a_noop(session):
    first = await apply_alert_signal(session, AlertSignal(scope="city", action="start", when=BASE))
    second = await apply_alert_signal(
        session, AlertSignal(scope="city", action="start", when=BASE + timedelta(minutes=5))
    )
    assert second is None  # no duplicate open alert, no second broadcast
    assert await _count(session, Alert) == 1
    await session.refresh(first)
    # SQLite round-trips datetimes tz-naive; compare wall-clock value only.
    assert first.started_at.replace(tzinfo=UTC) == BASE  # untouched by the redundant start


async def test_end_without_start_is_a_noop(session):
    result = await apply_alert_signal(session, AlertSignal(scope="city", action="end", when=BASE))
    assert result is None
    assert await _count(session, Alert) == 0


async def test_end_closes_the_open_alert(session):
    await apply_alert_signal(session, AlertSignal(scope="city", action="start", when=BASE))
    closed = await apply_alert_signal(
        session, AlertSignal(scope="city", action="end", when=BASE + timedelta(minutes=10))
    )
    assert closed is not None
    assert closed.ended_at == BASE + timedelta(minutes=10)
    assert closed.closed_reason == "official"


async def test_double_end_is_a_noop(session):
    await apply_alert_signal(session, AlertSignal(scope="city", action="start", when=BASE))
    await apply_alert_signal(
        session, AlertSignal(scope="city", action="end", when=BASE + timedelta(minutes=10))
    )
    second = await apply_alert_signal(
        session, AlertSignal(scope="city", action="end", when=BASE + timedelta(minutes=20))
    )
    assert second is None


async def test_city_and_oblast_are_independent(session):
    # Parallel city+oblast alerts must not interfere with each other's state.
    city = await apply_alert_signal(session, AlertSignal(scope="city", action="start", when=BASE))
    oblast = await apply_alert_signal(
        session, AlertSignal(scope="oblast", action="start", when=BASE + timedelta(minutes=1))
    )
    assert city is not None and oblast is not None
    assert city.id != oblast.id

    # Ending the city alert must not touch the still-open oblast one.
    await apply_alert_signal(
        session, AlertSignal(scope="city", action="end", when=BASE + timedelta(minutes=5))
    )
    open_alerts = list(await session.scalars(select(Alert).where(Alert.ended_at.is_(None))))
    assert len(open_alerts) == 1 and open_alerts[0].scope == "oblast"


async def test_a_new_start_after_end_reopens(session):
    # A real second siren cycle in the same scope opens a NEW alert row, not
    # a reuse of the closed one.
    await apply_alert_signal(session, AlertSignal(scope="city", action="start", when=BASE))
    await apply_alert_signal(
        session, AlertSignal(scope="city", action="end", when=BASE + timedelta(minutes=10))
    )
    second = await apply_alert_signal(
        session, AlertSignal(scope="city", action="start", when=BASE + timedelta(hours=1))
    )
    assert second is not None
    assert await _count(session, Alert) == 2


# --- failsafe ---

async def test_failsafe_closes_an_alert_open_past_the_limit(session):
    await apply_alert_signal(session, AlertSignal(scope="city", action="start", when=BASE))
    closed = await close_stale_alerts(session, BASE + timedelta(hours=13), hours=12)
    assert len(closed) == 1
    assert closed[0].closed_reason == "failsafe"
    assert closed[0].ended_at == BASE + timedelta(hours=13)


async def test_failsafe_leaves_a_fresh_alert_open(session):
    await apply_alert_signal(session, AlertSignal(scope="city", action="start", when=BASE))
    closed = await close_stale_alerts(session, BASE + timedelta(hours=2), hours=12)
    assert closed == []
    open_alerts = list(await session.scalars(select(Alert).where(Alert.ended_at.is_(None))))
    assert len(open_alerts) == 1


# --- ingest_alert_message: alert-channel messages never touch Threat/Notice ---

async def test_alert_message_creates_alert_not_threat_or_notice(session):
    out = await ingest_alert_message(
        session, text="‼️УВАГА! У Києві оголошена повітряна тривога!", when=BASE, message_id=1,
    )
    assert len(out) == 1 and out[0].type == "alert"
    assert await _count(session, Threat) == 0
    assert await _count(session, Notice) == 0
    assert await _count(session, Alert) == 1
    assert await _count(session, RawMessage) == 1


async def test_ordinary_city_news_is_dropped_without_touching_raw_messages(session):
    # Unlike the spotter pipeline's "raw storage first" discipline, the alert
    # channel's non-alert traffic (bulk city news) isn't kept at all — see
    # _alert_ingest_locked in ingest.py.
    out = await ingest_alert_message(
        session, text="🚠Із 13 липня фунікулер зачинять на ремонт", when=BASE, message_id=2,
    )
    assert out == []
    assert await _count(session, Alert) == 0
    assert await _count(session, RawMessage) == 0


async def test_duplicate_message_id_is_ignored(session):
    out1 = await ingest_alert_message(
        session, text="‼️УВАГА! У Києві оголошена повітряна тривога!", when=BASE, message_id=5,
    )
    out2 = await ingest_alert_message(
        session, text="‼️УВАГА! У Києві оголошена повітряна тривога!",
        when=BASE + timedelta(minutes=1), message_id=5,
    )
    assert len(out1) == 1
    assert out2 == []
    assert await _count(session, RawMessage) == 1
    assert await _count(session, Alert) == 1


# --- regions (migration 0036) ---
#
# An alert used to be Kyiv's by construction, and everything downstream — the
# banner, the journal's alert duration, the incident it adopts — inherited that
# assumption silently. These pin the behaviour the column exists for.

async def test_two_regions_can_be_under_alert_at_once(session):
    """The bug the column fixes at its root: `_find_open` keyed on scope alone,
    so an open Kyiv siren made every other region's start look like a repeat and
    no-op — a second region could never raise an alert while Kyiv's ran."""
    kyiv = await apply_alert_signal(
        session, AlertSignal(scope="city", action="start", when=BASE, region="kyiv"))
    sumy = await apply_alert_signal(
        session, AlertSignal(scope="city", action="start", when=BASE, region="sumy"))
    assert kyiv is not None and sumy is not None
    assert kyiv.id != sumy.id
    assert await _count(session, Alert) == 2


async def test_an_end_closes_only_its_own_region(session):
    await apply_alert_signal(
        session, AlertSignal(scope="city", action="start", when=BASE, region="kyiv"))
    await apply_alert_signal(
        session, AlertSignal(scope="city", action="start", when=BASE, region="sumy"))

    ended = await apply_alert_signal(
        session, AlertSignal(scope="city", action="end", when=BASE + timedelta(hours=1),
                             region="sumy"))
    assert ended is not None and ended.region == "sumy"
    still_open = list(await session.scalars(select(Alert).where(Alert.ended_at.is_(None))))
    assert [a.region for a in still_open] == ["kyiv"]


async def test_an_end_for_a_region_with_nothing_open_is_a_noop(session):
    await apply_alert_signal(
        session, AlertSignal(scope="city", action="start", when=BASE, region="kyiv"))
    assert await apply_alert_signal(
        session, AlertSignal(scope="city", action="end", when=BASE, region="sumy")) is None
    assert await _count(session, Alert) == 1


async def test_an_alert_defaults_to_the_home_region(session):
    """Every caller that predates regions still means what it always meant."""
    a = await apply_alert_signal(session, AlertSignal(scope="city", action="start", when=BASE))
    assert a is not None and a.region == "kyiv"


# --- raions (migration 0041) ---
#
# The district siren provider writes scope='raion' alerts, one per raion. Same
# shape of bug as the region one above, one level down.

async def test_two_raions_of_one_region_alert_independently(session):
    brovary = await apply_alert_signal(session, AlertSignal(
        scope="raion", action="start", when=BASE, region="kyiv",
        zone_id="kyiv-obl-brovarskyi"))
    vyshhorod = await apply_alert_signal(session, AlertSignal(
        scope="raion", action="start", when=BASE, region="kyiv",
        zone_id="kyiv-obl-vyshhorodskyi"))
    assert brovary is not None and vyshhorod is not None and brovary.id != vyshhorod.id


async def test_a_raion_end_closes_only_that_raion(session):
    await apply_alert_signal(session, AlertSignal(
        scope="raion", action="start", when=BASE, region="kyiv",
        zone_id="kyiv-obl-brovarskyi"))
    await apply_alert_signal(session, AlertSignal(
        scope="raion", action="start", when=BASE, region="kyiv",
        zone_id="kyiv-obl-vyshhorodskyi"))

    await apply_alert_signal(session, AlertSignal(
        scope="raion", action="end", when=BASE + timedelta(hours=1), region="kyiv",
        zone_id="kyiv-obl-brovarskyi"))
    still_open = list(await session.scalars(select(Alert).where(Alert.ended_at.is_(None))))
    assert [a.zone_id for a in still_open] == ["kyiv-obl-vyshhorodskyi"]


async def test_a_city_alert_is_not_found_by_a_raion_lookup(session):
    """NULL zone_id is a value in the key, not a wildcard — an official Kyiv
    alert must not be closed by the district provider clearing a raion."""
    city = await apply_alert_signal(
        session, AlertSignal(scope="city", action="start", when=BASE, region="kyiv"))
    ended = await apply_alert_signal(session, AlertSignal(
        scope="raion", action="end", when=BASE + timedelta(minutes=5), region="kyiv",
        zone_id="kyiv-obl-brovarskyi"))
    assert ended is None
    await session.refresh(city)
    assert city.ended_at is None


async def test_the_failsafe_leaves_raion_alerts_alone(session):
    """A >12 h siren is routine in the north, and the provider — polled every
    20 s — is the only thing entitled to close a raion alert. Force-closing one
    here would just be reopened on the next tick."""
    await apply_alert_signal(
        session, AlertSignal(scope="city", action="start", when=BASE, region="kyiv"))
    await apply_alert_signal(session, AlertSignal(
        scope="raion", action="start", when=BASE, region="sumy",
        zone_id="sumy-obl-sumskyi"))

    closed = await close_stale_alerts(session, BASE + timedelta(hours=20), 12)
    assert [a.scope for a in closed] == ["city"]
    still_open = list(await session.scalars(select(Alert).where(Alert.ended_at.is_(None))))
    assert [a.zone_id for a in still_open] == ["sumy-obl-sumskyi"]

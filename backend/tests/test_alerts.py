"""Tests for app/alerts.py (idempotent signal application, failsafe closure)
and app/ingest.py::ingest_alert_message (alert-channel messages only ever
create Alert rows — never a Threat or Notice, unlike the spotter pipeline).
"""

from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.domain.alerts import AlertSignal, close_stale_alerts
from app.domain.alerts import apply_alert_signal as _apply_signal
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


async def apply_alert_signal(session, signal: AlertSignal) -> Alert | None:
    """`domain.alerts.apply_alert_signal` unwrapped to the Alert row — most of
    this file is about the row itself. `AlertOutcome.kind` (opened / escalated /
    closed) has its own tests in the level section below."""
    outcome = await _apply_signal(session, signal)
    return outcome.alert if outcome is not None else None


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


# --- differentiated levels (migration 0046) ---
#
# «Окремий "Відбій" між різними видами загроз не оголошується» — the official
# channel replaces one announcement with the next, so a level moving inside a
# running siren must move the ROW, never open a second one.

async def test_a_start_carries_its_level_and_threat(session):
    a = await apply_alert_signal(session, AlertSignal(
        scope="city", action="start", when=BASE, level="yellow", threat="drone"))
    assert a.level == "yellow" and a.threat == "drone" and a.level_changed_at is None


async def test_an_escalation_moves_the_open_alert_instead_of_opening_one(session):
    opened = await _apply_signal(session, AlertSignal(
        scope="city", action="start", when=BASE, level="yellow", threat="drone"))
    escalated = await _apply_signal(session, AlertSignal(
        scope="city", action="start", when=BASE + timedelta(minutes=20),
        level="red", threat="missile"))
    assert escalated is not None and escalated.kind == "escalated"
    assert escalated.alert.id == opened.alert.id
    assert await _count(session, Alert) == 1
    assert escalated.alert.level == "red" and escalated.alert.threat == "missile"
    assert escalated.alert.level_changed_at == BASE + timedelta(minutes=20)
    # The siren is one continuous window — the journal and the banner both read
    # its duration off this.
    assert escalated.alert.started_at.replace(tzinfo=UTC) == BASE
    assert escalated.alert.ended_at is None


async def test_a_de_escalation_moves_the_row_the_same_way(session):
    await _apply_signal(session, AlertSignal(
        scope="city", action="start", when=BASE, level="red", threat="missile"))
    back = await _apply_signal(session, AlertSignal(
        scope="city", action="start", when=BASE + timedelta(minutes=30),
        level="yellow", threat="drone"))
    assert back is not None and back.kind == "escalated"
    assert back.alert.level == "yellow"
    assert await _count(session, Alert) == 1


async def test_repeating_the_same_level_is_still_a_noop(session):
    await _apply_signal(session, AlertSignal(
        scope="city", action="start", when=BASE, level="red", threat="missile"))
    again = await _apply_signal(session, AlertSignal(
        scope="city", action="start", when=BASE + timedelta(minutes=5),
        level="red", threat="missile"))
    assert again is None


async def test_a_levelless_start_never_erases_a_known_level(session):
    """A provider that grades nothing must not overwrite one that does — the
    district roster carrying a raion alerts.in.ua has stopped listing, or a
    non-Kyiv channel still posting the undifferentiated announcement."""
    await _apply_signal(session, AlertSignal(
        scope="city", action="start", when=BASE, level="red", threat="missile"))
    assert await _apply_signal(session, AlertSignal(
        scope="city", action="start", when=BASE + timedelta(minutes=5))) is None
    open_alert = (await session.scalars(select(Alert))).one()
    assert open_alert.level == "red" and open_alert.threat == "missile"


async def test_the_official_start_message_sets_the_level(session):
    await ingest_alert_message(
        session, text="🟡 УВАГА! У Києві оголошена дронова небезпека!",
        when=BASE, message_id=901)
    alert = (await session.scalars(select(Alert))).one()
    assert alert.level == "yellow" and alert.threat == "drone"


async def test_an_escalation_message_raises_a_feed_notice(session):
    await ingest_alert_message(
        session, text="🟡 УВАГА! У Києві оголошена дронова небезпека!",
        when=BASE, message_id=902)
    out = await ingest_alert_message(
        session, text="🔴 УВАГА! У Києві оголошена нова загроза — ракетна загроза!",
        when=BASE + timedelta(minutes=12), message_id=903)
    assert [b.type for b in out] == ["alert", "notice"]
    notice = (await session.scalars(
        select(Notice).where(Notice.kind == "alert_level"))).one()
    assert "ракетна загроза" in notice.text.lower()
    # The card is coloured by the level it moved TO, carried as a target family.
    assert notice.target_type == "missile"
    assert await _count(session, Alert) == 1


async def test_a_de_escalation_notice_carries_the_drone_family(session):
    await ingest_alert_message(
        session, text="🔴 УВАГА! У Києві оголошена ракетна загроза!",
        when=BASE, message_id=904)
    await ingest_alert_message(
        session, text="🟡 УВАГА! У Києві оголошена нова загроза — дронова небезпека!",
        when=BASE + timedelta(minutes=12), message_id=905)
    notice = (await session.scalars(
        select(Notice).where(Notice.kind == "alert_level"))).one()
    assert notice.target_type == "shahed"


# --- replaying history must not disturb a running alert ---
#
# A reconnect backfill replays a whole window of the channel, so the messages of
# a siren that finished days ago arrive while tonight's is running. On
# 2026-09-07 that put three alerts in the live DB, two of them stamped
# `ended_at` earlier than their own `started_at`.

async def test_an_old_stand_down_cannot_close_tonights_alert(session):
    live = await _apply_signal(session, AlertSignal(
        scope="city", action="start", when=BASE, level="red", threat="missile"))
    stale = await _apply_signal(session, AlertSignal(
        scope="city", action="end", when=BASE - timedelta(days=2)))
    assert stale is None
    await session.refresh(live.alert)
    assert live.alert.ended_at is None


async def test_a_raion_provider_may_still_close_what_it_opened(session):
    """The exemption: the district provider is polled, never replayed, so a
    timestamp disagreement there is its clock — and refusing would leave the
    siren burning with the reconciler retrying every 20 s."""
    await _apply_signal(session, AlertSignal(
        scope="raion", action="start", when=BASE, region="kyiv",
        zone_id="kyiv-obl-brovarskyi", level="yellow"))
    closed = await _apply_signal(session, AlertSignal(
        scope="raion", action="end", when=BASE - timedelta(hours=3), region="kyiv",
        zone_id="kyiv-obl-brovarskyi"))
    assert closed is not None and closed.alert.ended_at is not None


async def test_replaying_the_opening_announcement_does_not_undo_an_escalation(session):
    await _apply_signal(session, AlertSignal(
        scope="city", action="start", when=BASE, level="yellow", threat="drone"))
    await _apply_signal(session, AlertSignal(
        scope="city", action="start", when=BASE + timedelta(minutes=3),
        level="red", threat="missile"))

    # …and now the backfill hands us the жовтий announcement again.
    assert await _apply_signal(session, AlertSignal(
        scope="city", action="start", when=BASE, level="yellow", threat="drone")) is None
    # Re-delivering the escalation itself is just as stale — a second feed card
    # for one escalation is exactly what this prevents.
    assert await _apply_signal(session, AlertSignal(
        scope="city", action="start", when=BASE + timedelta(minutes=3),
        level="red", threat="missile")) is None

    alert = (await session.scalars(select(Alert))).one()
    assert alert.level == "red" and alert.threat == "missile"
    assert alert.started_at.replace(tzinfo=UTC) == BASE

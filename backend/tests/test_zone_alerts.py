"""Raion sirens becoming Alert rows: the flicker guard (domain/zone_alerts.py)
and the reconciliation that writes them (feeds/alert_zones.persist_once).

The provider is the untrusted input here, so most of these describe ways it
misbehaves — a state that blinks for one tick, a timestamp from last week, an
outage — and assert that the table stays clean.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.domain.alert_zones import ZONE_BY_ID, ZoneState
from app.domain.zone_alerts import (
    MAX_BACKDATE_HOURS,
    Pending,
    confirm_changes,
    eligible,
    signal_time,
)
from app.feeds import alert_zones as az
from app.models import Alert

BASE = datetime(2026, 9, 1, 20, 0, tzinfo=UTC)

BROVARY = "kyiv-obl-brovarskyi"
VYSHHOROD = "kyiv-obl-vyshhorodskyi"
NIZHYN = "chernihiv-obl-nizhynskyi"


def state(zone_id: str, alert: bool, changed_at: datetime | None = None) -> ZoneState:
    zone = ZONE_BY_ID[zone_id]
    return ZoneState(zone_id=zone.id, name_uk=zone.name_uk, oblast=zone.oblast,
                     alert=alert, changed_at=changed_at)


def observed(*states: ZoneState) -> dict[str, ZoneState]:
    return {s.zone_id: s for s in states}


# --- eligible ---

def test_kyiv_city_is_never_persisted_from_the_provider():
    """The official channel reports the same siren, sooner and better."""
    assert eligible(ZONE_BY_ID["kyiv-city"]) is False


def test_a_raion_of_an_active_region_is_eligible():
    assert eligible(ZONE_BY_ID[BROVARY]) is True
    assert eligible(ZONE_BY_ID[NIZHYN]) is True


def test_an_inactive_regions_raions_are_skipped():
    """Харківщина is declared but active=False — its rows would be read by
    nothing, so they are not written."""
    assert eligible(ZONE_BY_ID["kharkiv-obl-kharkivskyi"]) is False


# --- confirm_changes: the flicker guard ---

def test_a_sustained_change_confirms_after_the_required_ticks():
    pending, confirmed = confirm_changes({}, {}, observed(state(BROVARY, True)), 2)
    assert confirmed == []
    assert pending[BROVARY] == Pending(alert=True, ticks=1)

    pending, confirmed = confirm_changes(pending, {}, observed(state(BROVARY, True)), 2)
    assert [s.zone_id for s in confirmed] == [BROVARY]
    assert BROVARY not in pending  # committed on this tick, no longer a candidate


def test_a_single_tick_blink_never_confirms():
    """alert -> clear -> alert with nothing committed. The return leg cancels
    the candidate, so the counter restarts and no row is ever written."""
    pending, confirmed = confirm_changes({}, {}, observed(state(BROVARY, True)), 2)
    assert confirmed == []
    pending, confirmed = confirm_changes(pending, {}, observed(state(BROVARY, False)), 2)
    assert confirmed == [] and pending == {}
    pending, confirmed = confirm_changes(pending, {}, observed(state(BROVARY, True)), 2)
    assert confirmed == []
    assert pending[BROVARY].ticks == 1


def test_an_observation_matching_what_is_stored_is_not_a_change():
    pending, confirmed = confirm_changes({}, {BROVARY: True}, observed(state(BROVARY, True)), 2)
    assert confirmed == [] and pending == {}


def test_a_clear_confirms_the_same_way_a_start_does():
    committed = {BROVARY: True}
    pending, confirmed = confirm_changes({}, committed, observed(state(BROVARY, False)), 2)
    assert confirmed == []
    pending, confirmed = confirm_changes(pending, committed, observed(state(BROVARY, False)), 2)
    assert [s.zone_id for s in confirmed] == [BROVARY]


def test_zones_are_debounced_independently():
    snapshot = observed(state(BROVARY, True), state(NIZHYN, True))
    pending, _ = confirm_changes({}, {}, snapshot, 2)
    # Nizhyn drops back, Brovary holds.
    pending, confirmed = confirm_changes(
        pending, {}, observed(state(BROVARY, True), state(NIZHYN, False)), 2
    )
    assert [s.zone_id for s in confirmed] == [BROVARY]
    assert NIZHYN not in pending


def test_one_tick_is_enough_when_the_guard_is_disabled():
    _, confirmed = confirm_changes({}, {}, observed(state(BROVARY, True)), 1)
    assert [s.zone_id for s in confirmed] == [BROVARY]


def test_a_zone_missing_from_the_snapshot_is_left_alone():
    """Silence about a raion is not evidence about it."""
    pending, confirmed = confirm_changes({}, {BROVARY: True}, {}, 2)
    assert confirmed == [] and pending == {}


# --- signal_time ---

def test_the_providers_own_transition_instant_is_kept():
    began = BASE - timedelta(minutes=40)
    assert signal_time(state(BROVARY, True, began), BASE) == began


def test_a_missing_timestamp_falls_back_to_now():
    assert signal_time(state(BROVARY, True, None), BASE) == BASE


def test_a_future_timestamp_is_clamped_to_now():
    assert signal_time(state(BROVARY, True, BASE + timedelta(hours=2)), BASE) == BASE


def test_an_absurdly_old_timestamp_is_clamped():
    ancient = BASE - timedelta(days=9)
    assert signal_time(state(BROVARY, True, ancient), BASE) == BASE - timedelta(
        hours=MAX_BACKDATE_HOURS
    )


# --- persist_once: reconciliation against the DB ---

@pytest_asyncio.fixture
async def db(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'z.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(az, "SessionLocal", Session)
    yield Session
    await engine.dispose()


@pytest.fixture(autouse=True)
def _clean_state():
    az.reset_state()
    yield
    az.reset_state()


def _snapshot(*states: ZoneState) -> None:
    """Put the poller in the state one successful poll would leave it in."""
    az._states = observed(*states)
    az._last_ok = datetime.now(UTC)


async def _open_alerts(Session) -> list[Alert]:
    async with Session() as s:
        return list(await s.scalars(select(Alert).where(Alert.ended_at.is_(None))))


async def test_a_confirmed_start_writes_one_raion_alert(db, monkeypatch):
    monkeypatch.setattr(az.settings, "alert_zones_confirm_ticks", 1)
    began = datetime.now(UTC) - timedelta(minutes=25)
    _snapshot(state(BROVARY, True, began))

    changed = await az.persist_once()
    assert len(changed) == 1
    alert = changed[0]
    assert alert.scope == "raion" and alert.zone_id == BROVARY and alert.region == "kyiv"
    # The provider's own start time is kept, so the banner's clock is right.
    assert alert.started_at.replace(tzinfo=UTC) == began


async def test_a_repeat_poll_does_not_open_a_second_alert(db, monkeypatch):
    monkeypatch.setattr(az.settings, "alert_zones_confirm_ticks", 1)
    _snapshot(state(BROVARY, True))
    await az.persist_once()
    assert await az.persist_once() == []
    async with db() as s:
        assert await s.scalar(select(func.count()).select_from(Alert)) == 1


async def test_a_restart_mid_siren_does_not_duplicate(db, monkeypatch):
    """`committed` is re-read from the DB, not remembered — the in-memory
    counter being wiped by a redeploy must not re-open a running siren."""
    monkeypatch.setattr(az.settings, "alert_zones_confirm_ticks", 1)
    _snapshot(state(BROVARY, True))
    await az.persist_once()

    az._pending = {}  # what a process restart leaves behind
    _snapshot(state(BROVARY, True))
    assert await az.persist_once() == []
    async with db() as s:
        assert await s.scalar(select(func.count()).select_from(Alert)) == 1


async def test_a_clear_closes_the_raion_alert(db, monkeypatch):
    monkeypatch.setattr(az.settings, "alert_zones_confirm_ticks", 1)
    _snapshot(state(BROVARY, True))
    await az.persist_once()

    ended = datetime.now(UTC)
    _snapshot(state(BROVARY, False, ended))
    changed = await az.persist_once()
    assert len(changed) == 1 and changed[0].closed_reason == "official"
    assert await _open_alerts(db) == []


async def test_two_raions_of_one_oblast_alert_independently(db, monkeypatch):
    monkeypatch.setattr(az.settings, "alert_zones_confirm_ticks", 1)
    _snapshot(state(BROVARY, True), state(VYSHHOROD, True))
    await az.persist_once()
    assert {a.zone_id for a in await _open_alerts(db)} == {BROVARY, VYSHHOROD}

    _snapshot(state(BROVARY, True), state(VYSHHOROD, False))
    await az.persist_once()
    assert {a.zone_id for a in await _open_alerts(db)} == {BROVARY}


async def test_a_stale_provider_writes_nothing(db, monkeypatch):
    """An unreachable provider says nothing about a raion — and its silence
    must never read as an all-clear."""
    monkeypatch.setattr(az.settings, "alert_zones_confirm_ticks", 1)
    _snapshot(state(BROVARY, True))
    await az.persist_once()

    az._states = observed(state(BROVARY, False))
    az._last_ok = datetime.now(UTC) - timedelta(
        seconds=az.settings.alert_zones_stale_after_s + 60
    )
    assert await az.persist_once() == []
    assert [a.zone_id for a in await _open_alerts(db)] == [BROVARY]


async def test_a_blinking_provider_writes_nothing_at_the_default_guard(db):
    _snapshot(state(BROVARY, True))
    assert await az.persist_once() == []
    _snapshot(state(BROVARY, False))
    assert await az.persist_once() == []
    _snapshot(state(BROVARY, True))
    assert await az.persist_once() == []
    async with db() as s:
        assert await s.scalar(select(func.count()).select_from(Alert)) == 0


async def test_kyiv_city_never_reaches_the_table(db, monkeypatch):
    monkeypatch.setattr(az.settings, "alert_zones_confirm_ticks", 1)
    _snapshot(state("kyiv-city", True))
    assert await az.persist_once() == []

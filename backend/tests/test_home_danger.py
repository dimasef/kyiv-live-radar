"""Danger-near-home geometry + level assessment (app/domain/home_danger.py).

Pure in-memory ORM objects — no DB except the raion_id_for_point test. Points
are built from km offsets around a synthetic home so headings/distances are
exact by construction rather than depending on real gazetteer coordinates.
"""

import math
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db import Base
from app.domain.geometry import angdiff_deg, bearing_deg, haversine_km
from app.domain.home_danger import (
    DangerLevel,
    HomeZone,
    assess,
    has_movement,
    raion_id_for_point,
)
from app.models import District, Threat, ThreatEvent

BASE = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
KM_PER_DEG_LAT = math.pi / 180 * 6371.0  # ~111.19

HOME = HomeZone(lat=50.5, lon=30.5, radius_km=3.0)


def pt(km_south: float, km_east: float) -> tuple[float, float]:
    """A point offset from HOME by km (south-positive / east-positive)."""
    lat = HOME.lat - km_south / KM_PER_DEG_LAT
    lon = HOME.lon + km_east / (KM_PER_DEG_LAT * math.cos(math.radians(HOME.lat)))
    return lat, lon


def ev(km_south: float, km_east: float, minute: int, district_id: int = 99) -> ThreatEvent:
    lat, lon = pt(km_south, km_east)
    d = District(name_uk="т", name_en="t", lat=lat, lon=lon, aliases=[])
    return ThreatEvent(
        district=d, district_id=district_id, event_time=BASE + timedelta(minutes=minute)
    )


def track(*events: ThreatEvent, target_type: str = "shahed", scope: str = "district") -> Threat:
    t = Threat(target_type=target_type, scope=scope)
    t.events = list(events)
    return t


# --- geometry primitives ---

def test_haversine_known_values():
    assert haversine_km(50.5, 30.5, 50.5, 30.5) == 0.0
    one_deg_lat = haversine_km(50.5, 30.5, 51.5, 30.5)
    assert abs(one_deg_lat - KM_PER_DEG_LAT) < 0.01
    assert haversine_km(50.5, 30.5, 50.6, 30.7) == haversine_km(50.6, 30.7, 50.5, 30.5)


def test_bearing_cardinal_directions():
    north = pt(km_south=-10, km_east=0)
    east = pt(km_south=0, km_east=10)
    assert abs(bearing_deg(HOME.lat, HOME.lon, *north)) < 0.5
    assert abs(bearing_deg(HOME.lat, HOME.lon, *east) - 90) < 0.5


def test_angdiff_wraps():
    assert angdiff_deg(350, 10) == -20
    assert angdiff_deg(10, 350) == 20
    assert angdiff_deg(180, 0) == 180


# --- DANGER: proximity ---

def test_event_inside_radius_plus_buffer_is_danger():
    # radius 3 + buffer 2 = 5 km threshold; 4 km out -> DANGER
    assert assess(track(ev(4, 0, 0)), HOME) == DangerLevel.DANGER


def test_event_just_outside_buffer_is_not_danger():
    assert assess(track(ev(6, 0, 0)), HOME) == DangerLevel.NONE


# --- WARNING: vector ---

def test_track_heading_straight_at_home_warns():
    # 20 km south -> 15 km south: due north, straight at home
    assert assess(track(ev(20, 0, 0), ev(15, 0, 5)), HOME) == DangerLevel.WARNING


def test_track_heading_away_is_none():
    # moving due east while home is due north of the head
    assert assess(track(ev(15, -10, 0), ev(15, 0, 5)), HOME) == DangerLevel.NONE


def test_home_behind_track_is_none():
    # track passed home heading north: head is 13 km NORTH of home, still going north
    assert assess(track(ev(-8, 0, 0), ev(-13, 0, 5)), HOME) == DangerLevel.NONE


def test_track_that_left_home_area_is_no_longer_danger():
    """Proximity is about the CURRENT position: a track that flew through the
    home area and moved on (head now far, heading away) drops out of DANGER."""
    assert assess(track(ev(4, 0, 0), ev(-13, 0, 5)), HOME) == DangerLevel.NONE


def test_passing_10km_abeam_is_none():
    # due-north ray 10 km west of home: cross-track 10 > 3+3, angle ~33.7deg > 20
    assert assess(track(ev(20, -10, 0), ev(15, -10, 5)), HOME) == DangerLevel.NONE


def test_passing_4km_abeam_warns_via_slack():
    # cross-track 4 <= radius 3 + slack 3
    assert assess(track(ev(20, -4, 0), ev(15, -4, 5)), HOME) == DangerLevel.WARNING


def test_on_course_beyond_horizon_is_none():
    # straight at home but 30 km out (> projection horizon 20)
    assert assess(track(ev(35, 0, 0), ev(30, 0, 5)), HOME) == DangerLevel.NONE


def test_horizon_configurable(monkeypatch):
    monkeypatch.setattr(settings, "home_danger_projection_km", 40.0)
    assert assess(track(ev(35, 0, 0), ev(30, 0, 5)), HOME) == DangerLevel.WARNING


def test_same_time_enumeration_never_warns():
    """One message naming several districts produces same-time events — an
    enumeration, not a trajectory (mirror of frontend hasMovement)."""
    t = track(ev(20, 0, 0), ev(15, 0, 0), ev(10, 0, 0))
    assert not has_movement(t.events)
    assert assess(t, HOME) == DangerLevel.NONE


def test_mixed_naive_and_aware_event_times():
    """A live track mixes tz flavors: events loaded from SQLite are naive UTC,
    the event added in the CURRENT session carries an aware Telegram timestamp.
    assess/has_movement must normalize instead of raising TypeError (the
    2026-07-18 live-e2e crash) — and a same-instant enumeration split across
    the two flavors must still count as ONE timestamp, not movement."""
    naive_ev = ev(4, 0, 0)
    naive_ev.event_time = naive_ev.event_time.replace(tzinfo=None)
    t = track(naive_ev, ev(20, 0, 5))  # aware, latest, far away
    assert assess(t, HOME) == DangerLevel.NONE  # old 4-km point is not "now"

    same_instant_naive = ev(20, 0, 0)
    same_instant_naive.event_time = same_instant_naive.event_time.replace(tzinfo=None)
    t2 = track(same_instant_naive, ev(15, 0, 0))
    assert not has_movement(t2.events)


# --- DANGER: ballistic on the home raion ---

def test_ballistic_on_home_raion_is_danger_even_far():
    home = HomeZone(lat=HOME.lat, lon=HOME.lon, radius_km=3.0, raion_district_id=7)
    t = track(ev(12, 0, 0, district_id=7), target_type="ballistic")
    assert assess(t, home) == DangerLevel.DANGER


def test_ballistic_on_other_raion_is_not_danger():
    home = HomeZone(lat=HOME.lat, lon=HOME.lon, radius_km=3.0, raion_district_id=7)
    t = track(ev(12, 0, 0, district_id=8), target_type="ballistic")
    assert assess(t, home) == DangerLevel.NONE


def test_non_ballistic_on_home_raion_is_not_danger():
    home = HomeZone(lat=HOME.lat, lon=HOME.lon, radius_km=3.0, raion_district_id=7)
    t = track(ev(12, 0, 0, district_id=7), target_type="shahed")
    assert assess(t, home) == DangerLevel.NONE


# --- citywide excluded ---

def test_citywide_ballistic_is_none():
    t = track(ev(0, 0, 0), target_type="ballistic", scope="city")
    assert assess(t, HOME) == DangerLevel.NONE


# --- raion resolution (DB) ---

SQUARE = {
    "type": "Polygon",
    "coordinates": [[[30.4, 50.4], [30.6, 50.4], [30.6, 50.6], [30.4, 50.6], [30.4, 50.4]]],
}


@pytest_asyncio.fixture
async def session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'t.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        s.add(District(name_uk="Квадратний", name_en="Square", lat=50.5, lon=30.5,
                       aliases=[], boundary=SQUARE))
        s.add(District(name_uk="Безмежний", name_en="Pointonly", lat=51.0, lon=31.0,
                       aliases=[]))
        await s.commit()
        yield s
    await engine.dispose()


async def test_raion_id_for_point_inside(session):
    square_id = (await session.scalars(
        select(District.id).where(District.name_en == "Square"))).one()
    assert await raion_id_for_point(session, 50.5, 30.5) == square_id


async def test_raion_id_for_point_outside(session):
    assert await raion_id_for_point(session, 49.0, 29.0) is None

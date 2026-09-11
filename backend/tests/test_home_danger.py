"""Danger-near-home geometry + level assessment (app/domain/home_danger.py).

Pure in-memory ORM objects — no DB except the raion_id_for_point test. Points
are built from km offsets around a synthetic home so headings/distances are
exact by construction rather than depending on real gazetteer coordinates.
"""

import math
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy import select

from app.config import settings
from app.domain.geometry import angdiff_deg, bearing_deg, haversine_km
from app.domain.home_danger import (
    DangerLevel,
    HomeZone,
    assess,
    has_movement,
    raion_ids_for_zone,
)
from app.models import District, Threat, ThreatEvent
from app.timeutil import naive

BASE = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
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


def level(t: Threat, home: HomeZone, now: datetime | None = None) -> DangerLevel:
    """`assess` at the instant right after the track's newest sighting."""
    if now is None and t.events:
        now = max(naive(e.event_time) for e in t.events) + timedelta(seconds=1)
    return assess(t, home, now)[0]


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
    assert level(track(ev(4, 0, 0)), HOME) == DangerLevel.DANGER


def test_event_just_outside_buffer_is_not_danger():
    assert level(track(ev(6, 0, 0)), HOME) == DangerLevel.NONE


# --- WARNING: vector ---

def test_track_heading_straight_at_home_warns():
    # 20 km south -> 15 km south: due north, straight at home
    assert level(track(ev(20, 0, 0), ev(15, 0, 5)), HOME) == DangerLevel.WARNING


def test_track_heading_away_is_none():
    # moving due east while home is due north of the head
    assert level(track(ev(15, -10, 0), ev(15, 0, 5)), HOME) == DangerLevel.NONE


def test_home_behind_track_is_none():
    # track passed home heading north: head is 13 km NORTH of home, still going north
    assert level(track(ev(-8, 0, 0), ev(-13, 0, 5)), HOME) == DangerLevel.NONE


def test_track_that_left_home_area_is_no_longer_danger():
    """Proximity is about the CURRENT position: a track that flew through the
    home area and moved on (head now far, heading away) drops out of DANGER."""
    assert level(track(ev(4, 0, 0), ev(-13, 0, 5)), HOME) == DangerLevel.NONE


def test_passing_10km_abeam_is_none():
    # due-north ray 10 km west of home: cross-track 10 > 3+3, angle ~33.7deg > 20
    assert level(track(ev(20, -10, 0), ev(15, -10, 5)), HOME) == DangerLevel.NONE


def test_passing_4km_abeam_warns_via_slack():
    # cross-track 4 <= radius 3 + slack 3
    assert level(track(ev(20, -4, 0), ev(15, -4, 5)), HOME) == DangerLevel.WARNING


def test_on_course_beyond_horizon_is_none():
    # straight at home but 30 km out (> projection horizon 20)
    assert level(track(ev(35, 0, 0), ev(30, 0, 5)), HOME) == DangerLevel.NONE


def test_horizon_configurable(monkeypatch):
    monkeypatch.setattr(settings, "home_danger_projection_km", 40.0)
    assert level(track(ev(35, 0, 0), ev(30, 0, 5)), HOME) == DangerLevel.WARNING


def test_same_time_enumeration_never_warns():
    """One message naming several districts produces same-time events — an
    enumeration, not a trajectory (mirror of frontend hasMovement)."""
    t = track(ev(20, 0, 0), ev(15, 0, 0), ev(10, 0, 0))
    assert not has_movement(t.events)
    assert level(t, HOME) == DangerLevel.NONE


def test_mixed_naive_and_aware_event_times():
    """A live track mixes tz flavors: events loaded from SQLite are naive UTC,
    the event added in the CURRENT session carries an aware Telegram timestamp.
    assess/has_movement must normalize instead of raising TypeError (the
    2026-07-18 live-e2e crash) — and a same-instant enumeration split across
    the two flavors must still count as ONE timestamp, not movement."""
    naive_ev = ev(4, 0, 0)
    naive_ev.event_time = naive_ev.event_time.replace(tzinfo=None)
    t = track(naive_ev, ev(20, 0, 5))  # aware, latest, far away
    assert level(t, HOME) == DangerLevel.NONE  # old 4-km point is not "now"

    same_instant_naive = ev(20, 0, 0)
    same_instant_naive.event_time = same_instant_naive.event_time.replace(tzinfo=None)
    t2 = track(same_instant_naive, ev(15, 0, 0))
    assert not has_movement(t2.events)


# --- DANGER: ballistic on the home raion ---

def test_ballistic_on_home_raion_is_danger_even_far():
    home = HomeZone(lat=HOME.lat, lon=HOME.lon, radius_km=3.0, raion_district_ids=(7, 8))
    t = track(ev(12, 0, 0, district_id=7), target_type="ballistic")
    assert level(t, home) == DangerLevel.DANGER


def test_ballistic_on_second_overlapped_raion_is_danger():
    """A zone straddling a boundary guards ALL its raions, not just the one
    containing the home point."""
    home = HomeZone(lat=HOME.lat, lon=HOME.lon, radius_km=3.0, raion_district_ids=(7, 8))
    t = track(ev(12, 0, 0, district_id=8), target_type="ballistic")
    assert level(t, home) == DangerLevel.DANGER


def test_ballistic_on_other_raion_is_not_danger():
    home = HomeZone(lat=HOME.lat, lon=HOME.lon, radius_km=3.0, raion_district_ids=(7,))
    t = track(ev(12, 0, 0, district_id=8), target_type="ballistic")
    assert level(t, home) == DangerLevel.NONE


def test_non_ballistic_on_home_raion_is_not_danger():
    home = HomeZone(lat=HOME.lat, lon=HOME.lon, radius_km=3.0, raion_district_ids=(7,))
    t = track(ev(12, 0, 0, district_id=7), target_type="shahed")
    assert level(t, home) == DangerLevel.NONE


# --- citywide excluded ---

def test_citywide_ballistic_is_none():
    t = track(ev(0, 0, 0), target_type="ballistic", scope="city")
    assert level(t, HOME) == DangerLevel.NONE


# --- zone -> raion resolution (DB) ---

# Two adjacent squares sharing the meridian 30.5: West [30.3..30.5], East [30.5..30.7].
WEST_SQUARE = {
    "type": "Polygon",
    "coordinates": [[[30.3, 50.3], [30.5, 50.3], [30.5, 50.7], [30.3, 50.7], [30.3, 50.3]]],
}
EAST_SQUARE = {
    "type": "Polygon",
    "coordinates": [[[30.5, 50.3], [30.7, 50.3], [30.7, 50.7], [30.5, 50.7], [30.5, 50.3]]],
}


@pytest_asyncio.fixture
async def session(db_sessionmaker):
    async with db_sessionmaker() as s:
        s.add(District(name_uk="Захід", name_en="West", lat=50.5, lon=30.4,
                       aliases=[], boundary=WEST_SQUARE))
        s.add(District(name_uk="Схід", name_en="East", lat=50.5, lon=30.6,
                       aliases=[], boundary=EAST_SQUARE))
        s.add(District(name_uk="Безмежний", name_en="Pointonly", lat=51.0, lon=31.0,
                       aliases=[]))
        await s.commit()
        west = (await s.scalars(select(District.id).where(District.name_en == "West"))).one()
        east = (await s.scalars(select(District.id).where(District.name_en == "East"))).one()
        yield s, west, east


async def test_zone_deep_inside_one_raion(session):
    s, west, east = session
    # 30.4 is ~7 km from the 30.5 border — a 3 km zone stays fully in West
    assert await raion_ids_for_zone(s, 50.5, 30.4, 3.0) == [west]


async def test_zone_straddling_boundary_includes_both(session):
    s, west, east = session
    # centered on the shared meridian — roughly half the disc in each square
    assert await raion_ids_for_zone(s, 50.5, 30.5, 3.0) == sorted([west, east])


async def test_zone_barely_clipping_neighbour_ignores_it(session):
    s, west, east = session
    # center ~2.8 km west of the border with a 3 km radius: a single outer-ring
    # sample crosses it (4% of the disc) — under the 10% overlap threshold
    lon = 30.5 - 2.8 / (111.19 * math.cos(math.radians(50.5)))
    assert await raion_ids_for_zone(s, 50.5, lon, 3.0) == [west]


async def test_zone_outside_all_raions(session):
    s, *_ = session
    assert await raion_ids_for_zone(s, 49.0, 29.0, 3.0) == []


# --- path source ---

def sourced(source_id: int, km_south: float, km_east: float, minute: int) -> ThreatEvent:
    e = ev(km_south, km_east, minute)
    e.source_id = source_id
    return e


def test_warning_follows_the_path_source_not_the_echo():
    # Narrator (5) walks due north at home; echo (12) zigzags off to the east.
    t = track(
        sourced(5, 20, 0, 0), sourced(12, 18, 9, 1), sourced(5, 15, 0, 5), sourced(12, 14, -9, 6),
    )
    t.path_source_id = 5
    assert level(t, HOME) == DangerLevel.WARNING
    # All events (legacy NULL): the last leg is the echo's, pointing away.
    t.path_source_id = None
    assert level(t, HOME) == DangerLevel.NONE


def test_echo_only_movement_is_not_a_vector():
    t = track(sourced(5, 20, 0, 0), sourced(12, 18, 0, 1), sourced(12, 15, 0, 5))
    t.path_source_id = 5
    assert not has_movement(t.events, 5)
    assert level(t, HOME) == DangerLevel.NONE


# --- per-source current position (release E) ---

def sourced_at(source_id, km_south, km_east, minute, *, msg=None, reply=None):
    e = ev(km_south, km_east, minute)
    e.source_id, e.source_message_id, e.reply_to_message_id = source_id, msg, reply
    return e


def narrated(*events, target_type="shahed"):
    """Source 5 threads (a resolved reply), so it carries the tracked window."""
    return track(*events, target_type=target_type)


def test_narrator_near_home_is_danger_whatever_the_echo_says_later():
    t = narrated(sourced_at(5, 20, 0, 0, msg=1), sourced_at(5, 1, 0, 5, msg=2, reply=1),
                 sourced_at(12, 7, 0, 5))
    t.events[-1].event_time = BASE + timedelta(minutes=5, seconds=40)
    lvl, trigger = assess(t, HOME, BASE + timedelta(minutes=6))
    assert lvl == DangerLevel.DANGER and trigger is t.events[1]


def test_echo_near_home_is_danger_and_the_echo_is_the_trigger():
    t = narrated(sourced_at(5, 20, 0, 0, msg=1), sourced_at(5, 7, 0, 5, msg=2, reply=1),
                 sourced_at(12, 1, 0, 5))
    lvl, trigger = assess(t, HOME, BASE + timedelta(minutes=6))
    assert lvl == DangerLevel.DANGER and trigger is t.events[2]


def test_quiet_narrator_fix_still_places_a_shahed_five_minutes_on():
    t = narrated(sourced_at(5, 20, 0, 0, msg=1), sourced_at(5, 1, 0, 5, msg=2, reply=1),
                 sourced_at(12, 7, 0, 10))
    assert level(t, HOME, BASE + timedelta(minutes=10, seconds=30)) == DangerLevel.DANGER


def test_stale_echo_fix_near_home_no_longer_counts():
    # Echo (orphan, shahed window 5 min) was near home 8 min ago; narrator is 7 km out now.
    t = narrated(sourced_at(5, 20, 0, 0, msg=1), sourced_at(12, 1, 0, 2),
                 sourced_at(5, 7, 0, 10, msg=2, reply=1))
    assert level(t, HOME, BASE + timedelta(minutes=10, seconds=30)) == DangerLevel.NONE


def test_narrator_near_home_then_silence_stays_danger_within_its_window():
    t = narrated(sourced_at(5, 20, 0, 0, msg=1), sourced_at(5, 1, 0, 5, msg=2, reply=1))
    assert level(t, HOME, BASE + timedelta(minutes=10)) == DangerLevel.DANGER
    # Past the narrator's window the fix no longer places it — only the vector
    # still warns.
    assert level(t, HOME, BASE + timedelta(minutes=21)) == DangerLevel.WARNING


def test_an_echo_that_moved_on_overwrites_its_own_fix():
    t = track(sourced_at(12, 1, 0, 0), sourced_at(12, 7, 0, 2))
    assert level(t, HOME) == DangerLevel.NONE


def test_legacy_rule_reads_the_newest_cluster_only(monkeypatch):
    monkeypatch.setattr(settings, "danger_rule", "legacy")
    t = narrated(sourced_at(5, 20, 0, 0, msg=1), sourced_at(5, 1, 0, 5, msg=2, reply=1),
                 sourced_at(12, 7, 0, 6))
    assert level(t, HOME) == DangerLevel.NONE

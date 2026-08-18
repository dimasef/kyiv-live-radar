"""Unit tests for the shared staleness rule (app/domain/staleness.py).

Pure: the same rule the sweeper closes on and the API publishes as `stale_at`,
so a target's fade-out on the map lands exactly on its auto-close.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace

from app.domain.staleness import last_event_at, stale_at, stale_window_minutes

WINDOWS = {"minutes": 20, "ballistic_minutes": 5}


def _threat(*, target_type="shahed", scope="district", created_at=None, event_times=()):
    created = created_at or datetime(2026, 8, 18, 22, 0)
    return SimpleNamespace(
        target_type=target_type,
        scope=scope,
        created_at=created,
        events=[SimpleNamespace(event_time=t) for t in event_times],
    )


def test_district_ballistic_gets_the_short_window():
    assert stale_window_minutes("ballistic", "district", **WINDOWS) == 5


def test_citywide_ballistic_keeps_the_normal_window():
    # The city-scope ballistic track is the "barrage in progress" banner — its
    # waves can lull for minutes, so it must not clear on the short window.
    assert stale_window_minutes("ballistic", "city", **WINDOWS) == 20


def test_every_other_type_gets_the_normal_window():
    for target_type in ("shahed", "jet_drone", "missile", "unknown"):
        assert stale_window_minutes(target_type, "district", **WINDOWS) == 20


def test_no_ballistic_override_configured_falls_back_to_the_normal_window():
    assert stale_window_minutes("ballistic", "district", minutes=20) == 20


def test_last_event_at_is_the_latest_sighting():
    # Threat.events is ordered by event_time, so the tail is the latest.
    times = [datetime(2026, 8, 18, 22, 0), datetime(2026, 8, 18, 22, 7)]
    assert last_event_at(_threat(event_times=times)) == times[-1]


def test_last_event_at_falls_back_to_creation_for_an_eventless_track():
    created = datetime(2026, 8, 18, 21, 30)
    assert last_event_at(_threat(created_at=created)) == created


def test_stale_at_is_the_last_sighting_plus_the_window():
    seen = datetime(2026, 8, 18, 22, 7)
    shahed = _threat(event_times=[seen])
    ballistic = _threat(target_type="ballistic", event_times=[seen])
    assert stale_at(shahed, **WINDOWS) == seen + timedelta(minutes=20)
    assert stale_at(ballistic, **WINDOWS) == seen + timedelta(minutes=5)


def test_stale_at_can_be_in_the_past():
    # The sweep runs on an interval, so a track stays open for up to one tick
    # after crossing its window — the API must report that honestly rather than
    # clamping, or the map's fade would never bottom out.
    long_ago = datetime(2026, 8, 18, 20, 0)
    assert stale_at(_threat(event_times=[long_ago]), **WINDOWS) < datetime(2026, 8, 18, 22, 0)

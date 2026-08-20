"""Unit tests for the shared staleness rule (app/domain/staleness.py).

Pure: the same rule the sweeper closes on and the API publishes as `stale_at`,
so a target's fade-out on the map lands exactly on its auto-close.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace

from app.domain.staleness import (
    is_reply_tracked,
    last_event_at,
    stale_at,
    stale_window_minutes,
)

WINDOWS = {
    "orphan_windows": {"ballistic": 2, "missile": 3, "jet_drone": 3, "shahed": 5, "unknown": 6},
    "tracked_windows": {"ballistic": 5, "missile": 6, "jet_drone": 10, "shahed": 15,
                        "unknown": 20},
    "default_minutes": 20,
}


def _event(t, *, source_id=1, message_id=None, reply_to=None):
    return SimpleNamespace(
        event_time=t,
        source_id=source_id,
        source_message_id=message_id,
        reply_to_message_id=reply_to,
    )


def _threat(*, target_type="shahed", scope="district", created_at=None, events=()):
    created = created_at or datetime(2026, 8, 18, 22, 0)
    return SimpleNamespace(
        target_type=target_type, scope=scope, created_at=created, events=list(events)
    )


# --- which window applies -------------------------------------------------


def test_an_unfollowed_track_gets_the_short_window_for_its_type():
    for target_type, expected in (("ballistic", 2), ("missile", 3), ("jet_drone", 3),
                                  ("shahed", 5), ("unknown", 6)):
        assert stale_window_minutes(
            target_type, "district", tracked=False, **WINDOWS
        ) == expected


def test_a_reply_followed_track_gets_the_long_window_for_its_type():
    for target_type, expected in (("ballistic", 5), ("missile", 6), ("jet_drone", 10),
                                  ("shahed", 15), ("unknown", 20)):
        assert stale_window_minutes(
            target_type, "district", tracked=True, **WINDOWS
        ) == expected


def test_citywide_keeps_the_longest_window_whatever_its_type():
    # The city-scope track is the "barrage in progress" banner: it has no dot on
    # the map that could be wrong about where the target is, and its waves lull
    # for minutes — so neither the per-type nor the orphan window may shorten it,
    # reply chain or not.
    for target_type in ("ballistic", "missile", "jet_drone", "shahed", "unknown"):
        assert stale_window_minutes(target_type, "city", tracked=False, **WINDOWS) == 20
        assert stale_window_minutes(target_type, "city", tracked=True, **WINDOWS) == 20


def test_an_unmapped_target_type_falls_back_to_the_default():
    # A type added to the model but not to the windows must behave like the old
    # single-window world, not vanish in two minutes.
    assert stale_window_minutes("cruise_v2", "district", tracked=False, **WINDOWS) == 20
    assert stale_window_minutes("cruise_v2", "district", tracked=True, **WINDOWS) == 20


# --- what counts as "being followed" --------------------------------------


def test_a_single_sighting_is_not_tracked():
    assert not is_reply_tracked(_threat(events=[_event(datetime(2026, 8, 18, 22, 0),
                                                       message_id=10)]))


def test_a_resolved_reply_chain_is_tracked():
    t = _threat(events=[
        _event(datetime(2026, 8, 18, 22, 0), message_id=10),
        _event(datetime(2026, 8, 18, 22, 4), message_id=11, reply_to=10),
    ])
    assert is_reply_tracked(t)


def test_a_dangling_reply_is_not_tracked():
    # The parent was never parsed, so this reply STARTED the track rather than
    # joining one — nobody is walking this target along, and a broken chain must
    # not buy the long window.
    t = _threat(events=[_event(datetime(2026, 8, 18, 22, 0), message_id=11, reply_to=99)])
    assert not is_reply_tracked(t)


def test_a_reply_id_from_a_different_channel_is_not_tracked():
    # Telegram reply ids are channel-scoped: the same integer in another channel
    # is an unrelated message, so matching on the id alone would be a false link.
    t = _threat(events=[
        _event(datetime(2026, 8, 18, 22, 0), source_id=1, message_id=10),
        _event(datetime(2026, 8, 18, 22, 4), source_id=2, message_id=11, reply_to=10),
    ])
    assert not is_reply_tracked(t)


def test_corroboration_alone_is_not_tracked():
    # Two channels naming the same district within the corroboration window is
    # one snapshot seen twice, not evidence the target is being followed.
    t = _threat(events=[
        _event(datetime(2026, 8, 18, 22, 0), source_id=1, message_id=10),
        _event(datetime(2026, 8, 18, 22, 1), source_id=2, message_id=77),
    ])
    assert not is_reply_tracked(t)


# --- last seen / stale_at -------------------------------------------------


def test_last_event_at_is_the_latest_sighting():
    # Threat.events is ordered by event_time, so the tail is the latest.
    times = [datetime(2026, 8, 18, 22, 0), datetime(2026, 8, 18, 22, 7)]
    assert last_event_at(_threat(events=[_event(t) for t in times])) == times[-1]


def test_last_event_at_falls_back_to_creation_for_an_eventless_track():
    created = datetime(2026, 8, 18, 21, 30)
    assert last_event_at(_threat(created_at=created)) == created


def test_stale_at_is_the_last_sighting_plus_the_window():
    seen = datetime(2026, 8, 18, 22, 7)
    orphan = _threat(target_type="jet_drone", events=[_event(seen, message_id=10)])
    followed = _threat(target_type="jet_drone", events=[
        _event(datetime(2026, 8, 18, 22, 3), message_id=10),
        _event(seen, message_id=11, reply_to=10),
    ])
    assert stale_at(orphan, **WINDOWS) == seen + timedelta(minutes=3)
    assert stale_at(followed, **WINDOWS) == seen + timedelta(minutes=10)


def test_stale_at_can_be_in_the_past():
    # The sweep runs on an interval, so a track stays open for up to one tick
    # after crossing its window — the API must report that honestly rather than
    # clamping, or the map's fade would never bottom out.
    long_ago = datetime(2026, 8, 18, 20, 0)
    t = _threat(events=[_event(long_ago, message_id=1)])
    assert stale_at(t, **WINDOWS) < datetime(2026, 8, 18, 22, 0)

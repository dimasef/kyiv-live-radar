"""Which source draws a track's path (app/domain/path.py)."""

from datetime import UTC, datetime, timedelta

from app.config import settings
from app.domain.path import (
    dominant_source_id,
    narrator_source_id,
    path_events,
    path_source_id,
    refresh_path,
)
from app.models import Threat, ThreatEvent

BASE = datetime(2026, 8, 30, 9, 41, tzinfo=UTC)


def ev(source_id, minute, *, msg=None, reply=None, attached_by=None, frame=None):
    return ThreatEvent(
        source_id=source_id, district_id=1, event_time=BASE + timedelta(minutes=minute),
        source_message_id=msg, reply_to_message_id=reply, attached_by=attached_by, frame=frame,
    )


def test_narrator_is_the_source_of_the_last_resolved_reply():
    events = [ev(5, 0, msg=1), ev(12, 1, msg=7), ev(5, 3, msg=2, reply=1), ev(12, 4, msg=8)]
    assert narrator_source_id(events) == 5


def test_a_dangling_reply_is_not_a_narrator():
    assert narrator_source_id([ev(5, 0, msg=2, reply=1), ev(12, 1, msg=7)]) is None


def test_dominant_is_the_source_with_most_events():
    assert dominant_source_id([ev(12, 0), ev(12, 1), ev(13, 2)], None) == 12


def test_dominant_tie_goes_to_the_earlier_source():
    assert dominant_source_id([ev(13, 0), ev(12, 1)], None) == 13


def test_dominant_switches_only_with_a_lead_of_two():
    events = [ev(12, 0), ev(13, 1), ev(13, 2)]
    assert dominant_source_id(events, current=12) == 12
    events.append(ev(13, 3))
    assert dominant_source_id(events, current=12) == 13


def test_narrator_beats_the_dominant_source():
    events = [ev(12, 0), ev(12, 1), ev(12, 2), ev(5, 3, msg=1), ev(5, 4, msg=2, reply=1)]
    assert path_source_id(events, current=12) == 5


def test_path_events_keep_the_path_source_and_manual_placements():
    events = [ev(5, 0), ev(12, 1), ev(12, 2, attached_by="manual")]
    assert path_events(events, 5) == [events[0], events[2]]


def test_no_path_source_means_every_event():
    events = [ev(5, 0), ev(12, 1)]
    assert path_events(events, None) == events


def test_flag_off_draws_every_event(monkeypatch):
    monkeypatch.setattr(settings, "path_rule_enabled", False)
    events = [ev(5, 0), ev(12, 1)]
    assert path_events(events, 5) == events


def test_movement_is_read_off_the_path_source_only():
    t = Threat(target_type="shahed")
    t.events = [ev(5, 0, msg=1), ev(5, 1, msg=2, reply=1), ev(12, 2, frame="path")]
    refresh_path(t)
    assert t.path_source_id == 5
    assert t.movement_stated is False
    t.events.append(ev(5, 3, msg=3, reply=2, frame="path"))
    refresh_path(t)
    assert t.movement_stated is True

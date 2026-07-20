"""Unit tests for the pure per-day journal aggregation (app/domain/journal.py).

No DB — build_journal takes plain row-like objects, so lightweight
SimpleNamespace stand-ins are enough. Timestamps are naive UTC, exactly as rows
come back from SQLite in prod/dev.
"""

from datetime import date, datetime
from types import SimpleNamespace

from app.domain.journal import build_journal


def _threat(created_at, *, target_type="shahed", status="tracking", kind="track",
            scope="district", target_count=1):
    return SimpleNamespace(
        created_at=created_at, target_type=target_type, status=status,
        kind=kind, scope=scope, target_count=target_count,
    )


def _incident(started_at):
    return SimpleNamespace(started_at=started_at)


def _alert(started_at, ended_at, *, scope="city", closed_reason="official"):
    return SimpleNamespace(
        started_at=started_at, ended_at=ended_at, scope=scope, closed_reason=closed_reason,
    )


def _run(start, end, **kw):
    kw.setdefault("threats", [])
    kw.setdefault("incidents", [])
    kw.setdefault("alerts", [])
    kw.setdefault("district_events", [])
    days = build_journal(start, end, **kw)
    return {d.date: d for d in days}


def test_every_day_in_range_present_including_empty_middle():
    by_date = _run(date(2026, 7, 10), date(2026, 7, 12))
    assert list(by_date) == ["2026-07-10", "2026-07-11", "2026-07-12"]
    # A day with no activity is still present with zeroed stats.
    mid = by_date["2026-07-11"]
    assert mid.attack_count == 0 and mid.target_count == 0 and mid.district_count == 0


def test_kyiv_vs_utc_day_boundary():
    # 22:30 UTC on the 10th is 01:30 Kyiv on the 11th (summer, UTC+3) — must
    # bucket to the Kyiv day, not the UTC day.
    late = _threat(datetime(2026, 7, 10, 22, 30))
    by_date = _run(date(2026, 7, 10), date(2026, 7, 11), threats=[late])
    assert by_date["2026-07-10"].track_count == 0
    assert by_date["2026-07-11"].track_count == 1


def test_failsafe_and_open_alerts_counted_but_excluded_from_duration():
    good = _alert(datetime(2026, 7, 11, 8, 0), datetime(2026, 7, 11, 9, 0))
    failsafe = _alert(datetime(2026, 7, 11, 10, 0), datetime(2026, 7, 11, 22, 0),
                      closed_reason="failsafe")
    still_open = _alert(datetime(2026, 7, 11, 12, 0), None, closed_reason=None)
    # Deliberately out of chronological order — windows must come back sorted.
    by_date = _run(date(2026, 7, 11), date(2026, 7, 11),
                   alerts=[still_open, good, failsafe])
    day = by_date["2026-07-11"]
    assert day.alert_count == 3
    assert day.alert_seconds == 3600  # only the complete alert
    assert day.longest_alert_seconds == 3600
    assert day.alert_incomplete is True
    assert [w["started_at"].hour for w in day.alert_windows] == [8, 10, 12]
    assert [w["seconds"] for w in day.alert_windows] == [3600, 0, 0]  # incomplete stay 0
    assert [w["incomplete"] for w in day.alert_windows] == [False, True, True]
    assert day.alert_windows[2]["ended_at"] is None  # still open


def test_oblast_alerts_ignored():
    oblast = _alert(datetime(2026, 7, 11, 8, 0), datetime(2026, 7, 11, 9, 0), scope="oblast")
    by_date = _run(date(2026, 7, 11), date(2026, 7, 11), alerts=[oblast])
    assert by_date["2026-07-11"].alert_count == 0


def test_citywide_threat_excluded_from_counts():
    banner = _threat(datetime(2026, 7, 11, 12, 0), scope="city", target_type="ballistic")
    by_date = _run(date(2026, 7, 11), date(2026, 7, 11), threats=[banner])
    day = by_date["2026-07-11"]
    assert day.track_count == 0
    assert day.target_count == 0
    assert day.type_counts["ballistic"] == 0


def test_multi_type_day_with_impacts_and_group_sizes():
    threats = [
        _threat(datetime(2026, 7, 11, 1, 0), target_type="shahed", target_count=3),
        _threat(datetime(2026, 7, 11, 2, 0), target_type="ballistic",
                status="impact", kind="impact"),
        _threat(datetime(2026, 7, 11, 3, 0), target_type="missile", target_count=2),
    ]
    by_date = _run(date(2026, 7, 11), date(2026, 7, 11), threats=threats,
                   incidents=[_incident(datetime(2026, 7, 11, 0, 30))])
    day = by_date["2026-07-11"]
    assert day.attack_count == 1
    assert day.track_count == 2               # shahed + missile (impact excluded)
    assert day.target_count == 5              # 3 + 2
    assert day.impact_count == 1              # the ballistic impact
    assert day.type_counts["shahed"] == 1
    assert day.type_counts["ballistic"] == 1  # impacts still count toward the type mix
    assert day.type_counts["missile"] == 1


def test_districts_ordered_by_activity_and_sentinel_excluded():
    events = [
        (datetime(2026, 7, 11, 1, 0), 5),
        (datetime(2026, 7, 11, 2, 0), 8),
        (datetime(2026, 7, 11, 3, 0), 8),   # 8 is the most active district
        (datetime(2026, 7, 11, 4, 0), 8),
        (datetime(2026, 7, 11, 5, 0), 5),
        (datetime(2026, 7, 11, 6, 0), 3),
        (datetime(2026, 7, 11, 7, 0), 99),  # citywide sentinel — excluded
    ]
    by_date = _run(date(2026, 7, 11), date(2026, 7, 11),
                   district_events=events, sentinel_district_id=99)
    day = by_date["2026-07-11"]
    assert day.district_ids == [8, 5, 3]  # most-active first
    assert day.district_count == 3


def test_unknown_target_type_bucketed():
    weird = _threat(datetime(2026, 7, 11, 1, 0), target_type="something_new")
    by_date = _run(date(2026, 7, 11), date(2026, 7, 11), threats=[weird])
    assert by_date["2026-07-11"].type_counts["unknown"] == 1

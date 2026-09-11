"""Unit tests for the pure per-day journal aggregation (app/domain/journal.py).

No DB — build_journal takes plain row-like objects, so lightweight
SimpleNamespace stand-ins are enough. Timestamps are naive UTC, exactly as rows
come back from SQLite in prod/dev.
"""

from datetime import date, datetime
from types import SimpleNamespace

from app.domain.journal import build_journal
from app.domain.journal_window import JournalWindow


def _threat(created_at, *, target_type="shahed", status="tracking", kind="track",
            scope="district", target_count=1, closed_reason=None):
    return SimpleNamespace(
        created_at=created_at, target_type=target_type, status=status,
        kind=kind, scope=scope, target_count=target_count, closed_reason=closed_reason,
    )


def _incident(started_at, *, ended_reason=None):
    return SimpleNamespace(started_at=started_at, ended_reason=ended_reason)


def _alert(started_at, ended_at, *, scope="city", closed_reason="official"):
    return SimpleNamespace(
        started_at=started_at, ended_at=ended_at, scope=scope, closed_reason=closed_reason,
    )


def _run(start, end, **kw):
    window = JournalWindow(
        threats=kw.pop("threats", []),
        incidents=kw.pop("incidents", []),
        alerts=kw.pop("alerts", []),
        aftermath=kw.pop("aftermath", []),
        district_events=kw.pop("district_events", []),
        sentinel=kw.pop("sentinel_district_id", None),
        hide_impacts_from=kw.pop("hide_impacts_from", None),
        window_start=datetime.min,
        window_end=datetime.max,
    )
    days = build_journal(start, end, window, **kw)
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
        (datetime(2026, 7, 11, 1, 0), 5, False),
        (datetime(2026, 7, 11, 2, 0), 8, False),
        (datetime(2026, 7, 11, 3, 0), 8, False),   # 8 is the most active district
        (datetime(2026, 7, 11, 4, 0), 8, False),
        (datetime(2026, 7, 11, 5, 0), 5, False),
        (datetime(2026, 7, 11, 6, 0), 3, False),
        (datetime(2026, 7, 11, 7, 0), 99, False),  # citywide sentinel — excluded
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


def _report(reported_at, *, categories=("fire",)):
    return SimpleNamespace(reported_at=reported_at, categories=list(categories))


def test_aftermath_counted_per_category_and_per_report():
    """A report can name several things at once (7 of the 22 real ones do), so
    the two numbers answer different questions: how many reports, and how much
    of each kind. The categories therefore sum to MORE than the report count,
    and a UI reading either alone must not be surprised by the other."""
    by_date = _run(
        date(2026, 7, 6), date(2026, 7, 6),
        aftermath=[
            _report(datetime(2026, 7, 6, 4, 10), categories=("damage", "rescue", "casualties")),
            _report(datetime(2026, 7, 6, 5, 30), categories=("fire",)),
            _report(datetime(2026, 7, 6, 9, 0), categories=("fire", "damage")),
        ],
    )
    day = by_date["2026-07-06"]
    assert day.aftermath_count == 3
    assert day.aftermath_counts == {
        "casualties": 1, "rescue": 1, "fire": 2, "damage": 2,
    }


def test_aftermath_buckets_on_the_kyiv_day_it_was_reported():
    """Not the day of the strike it describes — we do not know that. A report
    filed at 00:30 Kyiv about the night before belongs to the new day, the same
    rule every other row in this file follows."""
    by_date = _run(
        date(2026, 7, 6), date(2026, 7, 7),
        # 21:40 UTC on the 6th is 00:40 Kyiv on the 7th.
        aftermath=[_report(datetime(2026, 7, 6, 21, 40), categories=("rescue",))],
    )
    assert by_date["2026-07-06"].aftermath_count == 0
    assert by_date["2026-07-07"].aftermath_count == 1


def test_aftermath_hidden_while_the_alert_is_still_on():
    """Same rule as impacts, same reason: «три пожежі в Дарницькому» during a
    running raid is the assessment a strike pin would be. Yesterday is reported
    normally — the withholding is about the raid in progress, not about the
    data."""
    by_date = _run(
        date(2026, 7, 5), date(2026, 7, 6),
        aftermath=[
            _report(datetime(2026, 7, 5, 10, 0), categories=("fire",)),
            _report(datetime(2026, 7, 6, 4, 0), categories=("fire", "casualties")),
        ],
        hide_impacts_from=date(2026, 7, 6),
    )
    assert by_date["2026-07-05"].aftermath_count == 1
    assert by_date["2026-07-06"].aftermath_count == 0
    assert by_date["2026-07-06"].aftermath_counts == {
        "casualties": 0, "rescue": 0, "fire": 0, "damage": 0,
    }


def test_aftermath_outside_the_range_is_ignored():
    by_date = _run(
        date(2026, 7, 6), date(2026, 7, 6),
        aftermath=[_report(datetime(2026, 7, 1, 12, 0), categories=("fire",))],
    )
    assert by_date["2026-07-06"].aftermath_count == 0


def test_an_unknown_category_is_dropped_not_counted():
    """The enum is the server's own, but a row written by an older build (or a
    category since removed) must not appear as a key nothing can render."""
    by_date = _run(
        date(2026, 7, 6), date(2026, 7, 6),
        aftermath=[_report(datetime(2026, 7, 6, 4, 0), categories=("fire", "power"))],
    )
    day = by_date["2026-07-06"]
    assert day.aftermath_count == 1
    assert "power" not in day.aftermath_counts
    assert day.aftermath_counts["fire"] == 1


def test_aftermath_does_not_touch_the_target_tallies():
    """A consequence is not a target. It must not reach track_count,
    target_count, the type mix or the district ranking — a day with three fires
    and no sighting is a day with no targets."""
    by_date = _run(
        date(2026, 7, 6), date(2026, 7, 6),
        aftermath=[_report(datetime(2026, 7, 6, 4, 0), categories=("fire", "damage"))],
    )
    day = by_date["2026-07-06"]
    assert (day.track_count, day.target_count, day.impact_count) == (0, 0, 0)
    assert day.district_count == 0
    assert sum(day.type_counts.values()) == 0

"""Unit tests for the pure across-days aggregation (app/domain/analytics.py).

No DB: build_analytics takes the DayStat rows build_journal already produced plus
plain tuples, so this composes the two pure functions the same way the route
does. Timestamps are naive UTC, exactly as rows come back from SQLite.
"""

from datetime import date, datetime
from types import SimpleNamespace

from app.domain.analytics import build_analytics, duration_bucket
from app.domain.journal import build_journal


def _threat(created_at, *, target_type="shahed", status="tracking", kind="track",
            scope="district", target_count=1, closed_reason=None):
    return SimpleNamespace(
        created_at=created_at, target_type=target_type, status=status,
        kind=kind, scope=scope, target_count=target_count, closed_reason=closed_reason,
    )


def _alert(started_at, ended_at, *, scope="city", closed_reason="official"):
    return SimpleNamespace(
        started_at=started_at, ended_at=ended_at, scope=scope, closed_reason=closed_reason,
    )


def _run(start, end, *, threats=(), incidents=(), alerts=(), district_events=(),
         target_first_seen=(), alert_start=None, sentinel_district_id=None):
    day_stats = build_journal(
        start, end,
        threats=list(threats), incidents=list(incidents), alerts=list(alerts),
        district_events=list(district_events), sentinel_district_id=sentinel_district_id,
    )
    return build_analytics(
        start, end,
        day_stats=day_stats,
        alert_windows=[(a.started_at, a.ended_at, a.closed_reason) for a in alerts],
        target_first_seen=list(target_first_seen),
        district_events=list(district_events),
        alert_start=alert_start,
        sentinel_district_id=sentinel_district_id,
    )


def test_alert_minutes_split_across_kyiv_midnight():
    # 20:30–22:30 UTC = 23:30 → 01:30 Kyiv (summer, UTC+3): half of hour 23, all
    # of hour 00, half of hour 01 — the window lands on both sides of midnight.
    stat = _run(
        date(2026, 7, 10), date(2026, 7, 11),
        alerts=[_alert(datetime(2026, 7, 10, 20, 30), datetime(2026, 7, 10, 22, 30))],
        alert_start=date(2026, 7, 10),
    )
    minutes = {h.hour: h.alert_minutes for h in stat.hours if h.alert_minutes}
    assert minutes == {23: 30, 0: 60, 1: 30}
    # The window is attributed to its Kyiv start day by build_journal, and its
    # duration is intact regardless of the midnight crossing.
    assert stat.totals.alert_seconds == 2 * 3600


def test_alert_minutes_survive_the_dst_fall_back():
    # Kyiv falls back 04:00->03:00 local on 2026-10-25 (01:00 UTC), so local hour
    # 03 happens twice. A 2-hour window across it must still report 2 hours —
    # wall-clock arithmetic reports 1 (the bug this test pins down).
    stat = _run(
        date(2026, 10, 25), date(2026, 10, 25),
        alerts=[_alert(datetime(2026, 10, 25, 0, 30), datetime(2026, 10, 25, 2, 30))],
        alert_start=date(2026, 10, 25),
    )
    assert sum(h.alert_minutes for h in stat.hours) == 120
    # 03:30 EEST (30 min) + the repeated 03:00 EET hour (60) + 04:00 EET (30).
    assert {h.hour: h.alert_minutes for h in stat.hours if h.alert_minutes} == {3: 90, 4: 30}


def test_alert_rates_normalize_on_the_alert_coverage_window_only():
    # 10 days of data, but the alert feed only starts on the 6th: the share of an
    # hour under alert must divide by 5 covered days, not 10.
    stat = _run(
        date(2026, 7, 1), date(2026, 7, 10),
        alerts=[_alert(datetime(2026, 7, 6, 5, 0), datetime(2026, 7, 6, 6, 0))],
        alert_start=date(2026, 7, 6),
    )
    assert stat.days_observed == 10
    assert stat.alert_days_observed == 5
    assert stat.alert_from_date == "2026-07-06"
    hour8 = next(h for h in stat.hours if h.hour == 8)  # 05:00 UTC = 08:00 Kyiv
    assert hour8.alert_minutes == 60
    assert hour8.alert_share == 60 / (5 * 60)


def test_incomplete_alerts_stay_out_of_duration_stats():
    complete = _alert(datetime(2026, 7, 11, 8, 0), datetime(2026, 7, 11, 9, 0))
    failsafe = _alert(
        datetime(2026, 7, 11, 10, 0), datetime(2026, 7, 11, 22, 0), closed_reason="failsafe"
    )
    still_open = _alert(datetime(2026, 7, 11, 15, 0), None)
    stat = _run(
        date(2026, 7, 11), date(2026, 7, 11),
        alerts=[complete, failsafe, still_open],
        alert_start=date(2026, 7, 11),
    )
    assert stat.totals.alerts == 3  # all three happened
    assert stat.totals.alert_seconds == 3600  # only the complete one has a duration
    assert stat.totals.alert_incomplete is True
    assert stat.alert_durations["1to2h"] == 1  # exactly 60 min is lower-inclusive
    assert sum(stat.alert_durations.values()) == 1
    assert stat.median_alert_seconds == 3600
    # The failsafe window's 12 hours must not appear in the hour-of-day picture.
    assert sum(h.alert_minutes for h in stat.hours) == 60


def test_duration_bucket_boundaries_are_lower_inclusive():
    assert duration_bucket(0) == "lt30"
    assert duration_bucket(29 * 60) == "lt30"
    assert duration_bucket(30 * 60) == "30to60"
    assert duration_bucket(59 * 60) == "30to60"
    assert duration_bucket(60 * 60) == "1to2h"
    assert duration_bucket(120 * 60) == "2to4h"
    assert duration_bucket(240 * 60) == "gt4h"
    assert duration_bucket(9 * 3600) == "gt4h"


def test_sentinel_district_excluded_and_districts_ranked_by_days():
    sentinel = 99
    events = [
        (datetime(2026, 7, 10, 6, 0), sentinel, False),
        (datetime(2026, 7, 10, 6, 0), 1, False),  # 1 district-day, 3 events
        (datetime(2026, 7, 10, 6, 5), 1, False),
        (datetime(2026, 7, 10, 6, 9), 1, True),
        (datetime(2026, 7, 10, 7, 0), 2, False),  # 2 district-days, 2 events
        (datetime(2026, 7, 11, 7, 0), 2, False),
    ]
    stat = _run(
        date(2026, 7, 10), date(2026, 7, 11),
        district_events=events, sentinel_district_id=sentinel,
    )
    assert [d.district_id for d in stat.districts] == [2, 1]
    assert (stat.districts[0].days, stat.districts[0].events) == (2, 2)
    assert (stat.districts[1].days, stat.districts[1].events) == (1, 3)
    assert stat.districts[1].impacts == 1


def test_targets_bin_by_first_sighting_and_count_group_size():
    stat = _run(
        date(2026, 7, 10), date(2026, 7, 10),
        target_first_seen=[
            (datetime(2026, 7, 10, 5, 0), 3),  # 08:00 Kyiv, a group of 3
            (datetime(2026, 7, 10, 5, 40), 1),
            (datetime(2026, 7, 9, 5, 0), 5),  # outside the period — ignored
        ],
    )
    assert next(h for h in stat.hours if h.hour == 8).target_count == 4
    assert sum(h.target_count for h in stat.hours) == 4


def test_quiet_streak_counts_only_covered_alert_free_days():
    # Alert coverage starts on the 3rd; alerts on the 3rd and the 8th, so the
    # longest alert-free run is the 4th-7th. The uncovered 1st-2nd don't count.
    alerts = [
        _alert(datetime(2026, 7, 3, 6, 0), datetime(2026, 7, 3, 7, 0)),
        _alert(datetime(2026, 7, 8, 6, 0), datetime(2026, 7, 8, 7, 0)),
    ]
    stat = _run(
        date(2026, 7, 1), date(2026, 7, 10), alerts=alerts, alert_start=date(2026, 7, 3)
    )
    assert stat.totals.quiet_streak_days == 4
    assert stat.totals.quiet_streak_from == "2026-07-04"
    assert stat.totals.quiet_streak_to == "2026-07-07"


def test_citywide_banners_and_dismissed_rows_do_not_inflate_totals():
    threats = [
        _threat(datetime(2026, 7, 10, 6, 0), target_count=2),
        _threat(datetime(2026, 7, 10, 6, 5), scope="city", target_count=9),
        _threat(datetime(2026, 7, 10, 6, 9), closed_reason="dismissed", target_count=9),
        _threat(datetime(2026, 7, 10, 7, 0), kind="impact", status="impact"),
    ]
    stat = _run(date(2026, 7, 10), date(2026, 7, 10), threats=threats)
    assert stat.totals.targets == 2
    assert stat.totals.tracks == 1
    assert stat.totals.impacts == 1
    assert stat.totals.active_days == 1
    assert stat.type_totals["shahed"] == 2  # the track and the impact
    assert stat.type_days["shahed"] == 1


def test_empty_period_is_all_zeros_without_dividing_by_zero():
    stat = _run(date(2026, 7, 1), date(2026, 7, 3))
    assert stat.days_observed == 3
    assert stat.alert_days_observed == 0
    assert stat.alert_from_date is None
    assert stat.totals.active_days == 0
    assert stat.totals.quiet_streak_days == 0
    assert stat.median_alert_seconds == 0 and stat.mean_alert_seconds == 0
    assert len(stat.hours) == 24
    assert all(h.alert_share == 0.0 for h in stat.hours)
    assert stat.districts == []

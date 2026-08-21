"""The attack banner's «цілі» number must mean targets, not tracks.

A spotter counting a group ("Знову 3 долітають до Броварів") produces ONE track
whose `target_count` is 3. The banner showed `track_count` under a label that
says "цілі", so a group of three read as one — visible on the map as a ×3 chip
next to a banner claiming a smaller number. `target_count` sums the stated group
sizes, the same way the journal totals targets, so the two agree.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from app.api.serialize import incident_out


def _threat(*, scope="district", kind="track", status="tracking", target_count=1, district_id=1):
    return SimpleNamespace(
        scope=scope,
        kind=kind,
        status=status,
        target_count=target_count,
        target_type="jet_drone",
        events=[SimpleNamespace(district_id=district_id)],
    )


def _incident(threats):
    return SimpleNamespace(
        id=1,
        started_at=datetime(2026, 8, 18, 18, 0),
        ended_at=None,
        ended_reason=None,
        target_type="jet_drone",
        attack_types=["jet_drone"],
        alert_id=None,
        decoy_mentions=0,
        has_hypersonic=False,
        threats=threats,
    )


def test_group_sizes_are_summed_into_target_count():
    # The real shape from the screenshot: two tracks, one of them a group of 3.
    out = incident_out(
        _incident([_threat(target_count=3, district_id=1), _threat(district_id=2)]),
        sentinel_district_id=None,
    )
    assert out.track_count == 2  # still two separate tracks
    assert out.target_count == 4  # …carrying four targets between them
    assert out.district_count == 2


def test_target_count_matches_track_count_when_nobody_counted():
    out = incident_out(_incident([_threat(), _threat(district_id=2)]), sentinel_district_id=None)
    assert (out.track_count, out.target_count) == (2, 2)


def test_a_missing_group_size_counts_as_one():
    out = incident_out(_incident([_threat(target_count=0)]), sentinel_district_id=None)
    assert out.target_count == 1


def test_impacts_and_citywide_banners_stay_out_of_both_counts():
    # Same exclusions as track_count: an impact is not an inbound target, and a
    # citywide banner is not a discrete one.
    out = incident_out(
        _incident(
            [
                _threat(target_count=2),
                _threat(kind="impact", status="impact", target_count=9),
                _threat(scope="city", target_count=9),
            ]
        ),
        sentinel_district_id=None,
    )
    assert out.track_count == 1
    assert out.target_count == 2
    assert out.citywide is True


def test_a_dismissed_impact_still_keeps_its_district_off_the_wire():
    # An admin dismissal rewrites `status` to 'dismissed' and leaves `kind`
    # alone. district_count used to be derived from `status` while district_ids
    # was derived from `kind`, so the strike raion vanished from the list but
    # was still counted — the two disagreed, and the count leaked what the list
    # exists to hide.
    out = incident_out(
        _incident(
            [
                _threat(district_id=1),
                _threat(kind="impact", status="dismissed", district_id=2),
            ]
        ),
        sentinel_district_id=None,
    )
    assert out.district_ids == [1]
    assert out.district_count == len(out.district_ids) == 1

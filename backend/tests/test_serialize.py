"""Unit tests for app/api/serialize.py::threat_out_shallow — a drift guard so
a new ThreatOut field is never silently dropped from the shallow (feed) path,
since it's built by introspecting ThreatOut.model_fields rather than a
hand-written list.

The freshness fields are the deliberate exception: they're derived from
`th.events`, which the shallow path never loads, so they stay NULL there. That
exclusion is asserted explicitly rather than left implicit."""

from datetime import UTC, datetime, timedelta

from app.api.serialize import _DERIVED_THREAT_FIELDS, threat_out, threat_out_shallow
from app.models import Threat
from app.schemas import ThreatOut


def _threat() -> Threat:
    th = Threat(
        target_type="shahed", status="tracking", kind="track",
        closed_reason=None, scope="district", region="kyiv", incident_id=None,
        target_count=2, closed_at=None, corroboration_count=2,
        has_conflict=True, confidence=0.75,
    )
    th.id = 42
    th.created_at = datetime(2026, 7, 11, 3, 52, tzinfo=UTC)
    th.events = []
    return th


def test_shallow_matches_full_output_minus_derived_fields():
    th = _threat()
    full = threat_out(th)
    shallow = threat_out_shallow(th)
    assert shallow.model_dump(exclude=_DERIVED_THREAT_FIELDS) == full.model_dump(
        exclude=_DERIVED_THREAT_FIELDS
    )
    assert shallow.events == []


def test_shallow_carries_every_stored_field():
    th = _threat()
    shallow = threat_out_shallow(th)
    for name in ThreatOut.model_fields:
        if name in _DERIVED_THREAT_FIELDS:
            continue
        assert getattr(shallow, name) == getattr(th, name), name


def test_only_the_full_serialization_publishes_freshness():
    th = _threat()
    shallow = threat_out_shallow(th)
    assert shallow.last_event_at is None and shallow.stale_at is None

    full = threat_out(th)
    # No events yet -> last seen is the creation time, and with no reply chain to
    # show for itself the fade spans a shahed's short window (domain/staleness.py).
    assert full.last_event_at == th.created_at
    assert full.stale_at == th.created_at + timedelta(minutes=5)

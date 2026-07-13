"""Unit tests for app/api/serialize.py::threat_out_shallow — a drift guard so
a new ThreatOut field is never silently dropped from the shallow (feed) path,
since it's built by introspecting ThreatOut.model_fields rather than a
hand-written list."""

from datetime import datetime, timezone

from app.api.serialize import threat_out, threat_out_shallow
from app.models import Threat
from app.schemas import ThreatOut


def _threat() -> Threat:
    th = Threat(
        target_type="shahed", status="tracking", kind="track",
        closed_reason=None, scope="district", incident_id=None,
        target_count=2, closed_at=None, corroboration_count=2,
        has_conflict=True, confidence=0.75,
    )
    th.id = 42
    th.created_at = datetime(2026, 7, 11, 3, 52, tzinfo=timezone.utc)
    th.events = []
    return th


def test_shallow_matches_full_output_minus_events():
    th = _threat()
    full = threat_out(th)
    shallow = threat_out_shallow(th)
    assert shallow.model_dump(exclude={"events"}) == full.model_dump(exclude={"events"})
    assert shallow.events == []


def test_shallow_carries_every_non_events_field():
    th = _threat()
    shallow = threat_out_shallow(th)
    for name in ThreatOut.model_fields:
        if name == "events":
            continue
        assert getattr(shallow, name) == getattr(th, name), name

"""Unit tests for app/domain/fusion.py — corroboration count, origin dedup
(repost collapse + same-channel collapse), conflict detection, and that the
confidence weights actually come from config.py (not hardcoded)."""

from app.config import settings
from app.domain.fusion import compute_fusion
from app.models import ThreatEvent


def _ev(source_id=None, event_target_type="shahed", forwarded_from_id=None,
        forwarded_from_channel_id=None, source_message_id=None):
    return ThreatEvent(
        threat_id=1, district_id=1, source_id=source_id,
        event_target_type=event_target_type,
        forwarded_from_id=forwarded_from_id,
        forwarded_from_channel_id=forwarded_from_channel_id,
        source_message_id=source_message_id,
    )


def test_single_source_uses_one_source_confidence():
    r = compute_fusion([_ev(source_id=1, source_message_id=100)])
    assert r.corroboration_count == 1
    assert r.confidence == settings.fusion_conf_one_source


def test_two_independent_sources_corroborate():
    events = [
        _ev(source_id=1, source_message_id=100),
        _ev(source_id=2, source_message_id=200),
    ]
    r = compute_fusion(events)
    assert r.corroboration_count == 2
    assert r.confidence == settings.fusion_conf_two_sources
    assert not r.has_conflict


def test_three_plus_sources_use_the_top_confidence_tier():
    events = [
        _ev(source_id=1, source_message_id=100),
        _ev(source_id=2, source_message_id=200),
        _ev(source_id=3, source_message_id=300),
    ]
    r = compute_fusion(events)
    assert r.corroboration_count == 3
    assert r.confidence == settings.fusion_conf_three_plus_sources


def test_repost_of_the_same_original_does_not_inflate_corroboration():
    # A repost (aggregator channel) carries forwarded_from_id pointing at the
    # ORIGINAL event's own source_message_id — same origin, must collapse to
    # ONE independent source, not two.
    original = _ev(source_id=1, source_message_id=100)
    repost = _ev(source_id=99, forwarded_from_id=100)
    r = compute_fusion([original, repost])
    assert r.corroboration_count == 1
    assert r.confidence == settings.fusion_conf_one_source


def test_repeated_messages_from_the_same_channel_do_not_inflate_corroboration():
    # A single channel narrating one track over time (sighting -> update ->
    # destroyed) is ONE origin, not one per message.
    events = [
        _ev(source_id=1, source_message_id=100),
        _ev(source_id=1, source_message_id=101),
        _ev(source_id=1, source_message_id=102),
    ]
    r = compute_fusion(events)
    assert r.corroboration_count == 1


def test_disagreeing_target_types_flag_a_conflict():
    events = [
        _ev(source_id=1, source_message_id=100, event_target_type="shahed"),
        _ev(source_id=2, source_message_id=200, event_target_type="missile"),
    ]
    r = compute_fusion(events)
    assert r.has_conflict
    assert r.confidence == round(
        settings.fusion_conf_two_sources - settings.fusion_conflict_penalty, 2
    )


def test_ballistic_and_missile_are_the_same_family_not_a_conflict():
    # Ballistic is a specialization of missile — one source saying "ракети"
    # and another saying "балістичні С-400" describe the SAME salvo.
    events = [
        _ev(source_id=1, source_message_id=100, event_target_type="missile"),
        _ev(source_id=2, source_message_id=200, event_target_type="ballistic"),
    ]
    r = compute_fusion(events)
    assert not r.has_conflict


def test_shahed_and_jet_drone_are_the_same_family_not_a_conflict():
    # A bare «БпЛА» parses as shahed, so «Реактивний БпЛА зі сторони
    # Славутича» + «БпЛА на Славутич» about one target read as different
    # specificity of the same drone callout, not a disagreement (the live
    # track-274 false conflict, 2026-07-18).
    events = [
        _ev(source_id=1, source_message_id=100, event_target_type="jet_drone"),
        _ev(source_id=2, source_message_id=200, event_target_type="shahed"),
    ]
    r = compute_fusion(events)
    assert not r.has_conflict
    assert r.confidence == settings.fusion_conf_two_sources


def test_drone_vs_missile_still_flags_a_conflict():
    events = [
        _ev(source_id=1, source_message_id=100, event_target_type="jet_drone"),
        _ev(source_id=2, source_message_id=200, event_target_type="ballistic"),
    ]
    assert compute_fusion(events).has_conflict


def test_unknown_target_type_never_counts_as_a_conflicting_claim():
    events = [
        _ev(source_id=1, source_message_id=100, event_target_type="shahed"),
        _ev(source_id=2, source_message_id=200, event_target_type="unknown"),
    ]
    r = compute_fusion(events)
    assert not r.has_conflict


def test_confidence_weights_come_from_config(monkeypatch):
    monkeypatch.setattr(settings, "fusion_conf_one_source", 0.42)
    r = compute_fusion([_ev(source_id=1, source_message_id=100)])
    assert r.confidence == 0.42


def test_conflict_penalty_comes_from_config(monkeypatch):
    monkeypatch.setattr(settings, "fusion_conflict_penalty", 0.05)
    events = [
        _ev(source_id=1, source_message_id=100, event_target_type="shahed"),
        _ev(source_id=2, source_message_id=200, event_target_type="missile"),
    ]
    r = compute_fusion(events)
    assert r.confidence == round(settings.fusion_conf_two_sources - 0.05, 2)

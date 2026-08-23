"""Ingest pipeline package (one raw message -> stored + parsed + tracked +
broadcast). Split into context / resolve / handlers / core / alert; re-exports the
public API so every existing `from app.pipeline.ingest import …` keeps working."""

from __future__ import annotations

from ..lock import ingest_lock
from .alert import ingest_alert_message, process_parsed_alert
from .context import (
    TypeContext,
    _note_and_inherit_type,
    _recent_type,
    note_inferred_type,
    note_operator_type,
    note_type_decline,
    rehydrate_type_context,
    reset_type_context,
    type_context_declined,
)
from .core import ingest_message, process_parsed, process_rescued
from .resolve import should_fallback

__all__ = [
    "ingest_message",
    "ingest_alert_message",
    "process_parsed",
    "process_parsed_alert",
    "process_rescued",
    "should_fallback",
    "ingest_lock",
    "_note_and_inherit_type",
    "note_inferred_type",
    "note_operator_type",
    "note_type_decline",
    "type_context_declined",
    "reset_type_context",
    "TypeContext",
    "rehydrate_type_context",
    "_recent_type",
]

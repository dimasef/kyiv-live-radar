"""Ingest pipeline package (one raw message -> stored + parsed + tracked +
broadcast). Split into context / resolve / handlers / core / alert; re-exports the
public API so every existing `from app.pipeline.ingest import …` keeps working."""

from __future__ import annotations

from ..lock import _ingest_lock
from .alert import ingest_alert_message, process_parsed_alert
from .context import _note_and_inherit_type, _recent_type
from .core import ingest_message, process_parsed, process_rescued
from .resolve import should_fallback

__all__ = [
    "ingest_message",
    "ingest_alert_message",
    "process_parsed",
    "process_parsed_alert",
    "process_rescued",
    "should_fallback",
    "_ingest_lock",
    "_note_and_inherit_type",
    "_recent_type",
]

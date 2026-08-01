"""The one helper every schema module shares: UTC re-attachment on
serialization."""

from __future__ import annotations

from datetime import UTC, datetime


def _as_utc(v: object) -> object:
    """SQLite drops tzinfo on round-trip even with DateTime(timezone=True) —
    every stored datetime is UTC wall-clock, just naive by the time it gets
    here. Reattach UTC before serialization so API responses carry an
    explicit offset ('Z'/'+00:00') instead of an ambiguous naive string the
    frontend would otherwise misinterpret as browser-local time."""
    if isinstance(v, datetime) and v.tzinfo is None:
        return v.replace(tzinfo=UTC)
    return v

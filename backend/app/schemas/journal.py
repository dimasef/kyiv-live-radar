"""Per-day journal aggregation payloads."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator

from .base import _as_utc


class JournalAlertWindowOut(BaseModel):
    """One тривога→відбій window within a journal day. `seconds` stays 0 for an
    incomplete window (still open / failsafe-closed) so it can never be picked
    as the day's longest."""

    started_at: datetime
    ended_at: datetime | None = None
    seconds: int = 0
    incomplete: bool = False

    _tz_window = field_validator("started_at", "ended_at", mode="before")(_as_utc)


class JournalDayOut(BaseModel):
    """One calendar day of aggregated threat activity — see GET /journal/days.
    Mirrors app/domain/journal.py::DayStat. The intensity score is derived on
    the client from these fields (the frontend owns the weighting)."""

    date: str  # Kyiv-local ISO date, YYYY-MM-DD
    attack_count: int = 0
    track_count: int = 0
    target_count: int = 0
    impact_count: int = 0
    # What those strikes DID — reports of fires / damage / rescue work /
    # casualties, keyed by AFTERMATH_CATEGORIES. Held back by the same rule as
    # `impact_count` while a city alert is running (see domain/journal.py), and
    # counts only: the journal never says WHICH raion burned, which is what
    # keeps a day's numbers from becoming the strike map they exist instead of.
    aftermath_counts: dict[str, int] = {}
    # Reports, not categories — one report can name several, so the values above
    # sum to more than this.
    aftermath_count: int = 0
    # Per-target-type threat counts, keyed by TARGET_TYPES (shahed/jet_drone/
    # missile/ballistic/unknown) — feeds the day's type-breakdown bar.
    type_counts: dict[str, int] = {}
    alert_count: int = 0
    alert_seconds: int = 0
    longest_alert_seconds: int = 0
    # A day's alert duration is a lower bound when some alert was still open or
    # failsafe-closed (see ALERT_CLOSED_REASONS) — the UI prefixes "≥".
    alert_incomplete: bool = False
    # Chronological тривога→відбій intervals — the UI lists each one.
    alert_windows: list[JournalAlertWindowOut] = []
    # Most-active district first (by event count), so a "top districts" UI can
    # just take the head of the list.
    district_ids: list[int] = []
    district_count: int = 0


class JournalOut(BaseModel):
    """GET /journal/days — every day in [from_date, to_date] inclusive, with
    zero-activity days present (as empty stats) so the calendar renders gaps."""

    from_date: str
    to_date: str
    days: list[JournalDayOut]

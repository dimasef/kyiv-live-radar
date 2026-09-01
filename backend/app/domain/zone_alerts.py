"""Turning the district provider's raion snapshot into `Alert` rows.

Pure and side-effect free on purpose — the poller (`feeds/alert_zones.py`) owns
the network and the DB, this owns the decision. The decision is only interesting
because the provider is not trustworthy tick by tick: it disagrees with itself
between its two sources, and a raion can blink alert->clear->alert inside a
minute. Painting that on a map is harmless; writing it into a table that feeds
the banner, the feed and (later) push notifications is not.

So a raion has to HOLD a state that differs from what we have stored for
`ticks_required` consecutive polls before it earns a transition. At 20 s per poll
the default of 2 costs ~40 s of latency and swallows every single-tick blink.

`committed` is read from the DB each tick rather than remembered in memory: the
reconciliation is then naturally restart-safe (a redeploy mid-siren re-derives
what it already knows) and self-healing (a write that failed is simply retried
next tick).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ..regions import active_regions
from ..timeutil import naive
from .alert_zones import KYIV_CITY_ZONE_ID, ZONES, Zone, ZoneState, region_of

# How far back the provider's own `changed_at` may be believed. A raion alerting
# for six hours when we boot is real and its start time is worth keeping; a
# timestamp older than this is a provider bug, not a day-long siren we slept
# through, and backdating an alert that far would poison every duration shown.
MAX_BACKDATE_HOURS = 24


@dataclass(frozen=True)
class Pending:
    """A state the provider is reporting that we have not committed yet."""

    alert: bool
    ticks: int


def eligible(zone: Zone) -> bool:
    """Whether this raion's siren may become an `Alert` row.

    Kyiv city is excluded because the official Telegram channel reports the same
    siren, sooner and more reliably — two providers writing the same window would
    only give the banner a choice it has no basis to make. Regions that are
    declared but not yet active are excluded so a switched-off oblast does not
    quietly fill the table with rows nothing reads.
    """
    if zone.id == KYIV_CITY_ZONE_ID:
        return False
    return region_of(zone) in {spec.id for spec in active_regions()}


def confirm_changes(
    pending: dict[str, Pending],
    committed: dict[str, bool],
    observed: dict[str, ZoneState],
    ticks_required: int,
) -> tuple[dict[str, Pending], list[ZoneState]]:
    """One tick of the debounce.

    `committed` is what the DB says is open per raion, `observed` this poll's
    snapshot. Returns the pending map to carry into the next tick, and the states
    whose change has now been confirmed and should be written.

    A zone whose observation matches what is committed simply drops out of
    `pending` — that is what makes a blink free: the return leg cancels the
    candidate raised by the outbound one, and the counter starts from zero when
    it comes back.
    """
    next_pending: dict[str, Pending] = {}
    confirmed: list[ZoneState] = []
    for zone in ZONES:
        if not eligible(zone):
            continue
        state = observed.get(zone.id)
        if state is None:
            continue
        if state.alert == committed.get(zone.id, False):
            continue
        prev = pending.get(zone.id)
        ticks = prev.ticks + 1 if prev is not None and prev.alert == state.alert else 1
        if ticks >= ticks_required:
            confirmed.append(state)
        else:
            next_pending[zone.id] = Pending(alert=state.alert, ticks=ticks)
    return next_pending, confirmed


def signal_time(state: ZoneState, now: datetime) -> datetime:
    """When this transition actually happened, per the provider.

    Preferring the provider's `changed_at` over `now` is what makes a restart
    mid-siren show the true duration instead of restarting the clock. Clamped
    both ways: a future stamp is a clock disagreement, and anything older than
    `MAX_BACKDATE_HOURS` is a provider bug (see the constant).
    """
    when = state.changed_at
    if when is None:
        return now
    if naive(when) > naive(now):
        return now
    if naive(when) < naive(now) - timedelta(hours=MAX_BACKDATE_HOURS):
        return now - timedelta(hours=MAX_BACKDATE_HOURS)
    return when

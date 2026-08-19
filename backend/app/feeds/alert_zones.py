"""Polls an external provider for the siren state of the watched raions and
pushes changes to the map.

Read-only situational context — see domain/alert_zones.py for why this is a
separate layer from `Alert` and why nothing is persisted. The loop follows
pipeline/sweeper.py (sleep, one guarded body, never let an exception kill the
task) and the httpx conventions of auth/providers/google.py (short timeout,
client per call).

Two provider shapes:
  * `skog` (primary) — a FULL snapshot: every oblast with every raion, alerted
    or not, each with the instant it last changed. Timestamps are naive Kyiv
    local time.
  * `aiu` (fallback) — alerts.in.ua's ACTIVE alerts only, ISO-UTC. A zone it
    doesn't list is inferred clear, which is why it is a fallback: it cannot
    tell "clear since 21:56" from "clear as far as I know".
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import datetime

import httpx

from ..api.ws import manager
from ..config import settings
from ..domain.alert_zones import (
    WATCHED_OBLASTS,
    ZONE_BY_PLACE,
    ZONES,
    ZoneState,
    unknown_state,
)
from ..models import utcnow
from ..schemas import AlertZoneOut, WSMessage
from ..timeutil import from_kyiv_local

log = logging.getLogger("alert_zones")

_SKOG_TIME = "%Y-%m-%d %H:%M:%S"
# The provider stamps "never observed a change" as the unix epoch in Kyiv time.
_EPOCH_YEAR = 1971

_states: dict[str, ZoneState] = {}
_last_ok: datetime | None = None
_unknown_places: set[tuple[str, str]] = set()


def _parse_skog_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.strptime(value, _SKOG_TIME)
    except ValueError:
        return None
    if dt.year < _EPOCH_YEAR:
        return None
    return from_kyiv_local(dt)


def _note_unknown(oblast: str, name: str) -> None:
    """Log an unrecognized raion once. A rename or a new raion upstream is worth
    seeing, but not once every 20 seconds forever."""
    key = (oblast, name)
    if key not in _unknown_places:
        _unknown_places.add(key)
        log.warning("alert zone not in the roster: %s / %s", oblast, name)


def parse_skog(payload: dict) -> dict[str, ZoneState]:
    """Full snapshot -> {zone_id: state}. Pure; the poller does the I/O."""
    states: dict[str, ZoneState] = {}
    for entry in (payload.get("raw") or {}).values():
        oblast = entry.get("name")
        if oblast not in WATCHED_OBLASTS:
            continue
        rows = entry.get("districts") or []
        if not rows:
            # Kyiv city has no raion split in the alert system — the whole city
            # alerts as one, so the oblast-level entry IS the zone.
            rows = [{"name": oblast, "alert": entry.get("alert"),
                     "changed": entry.get("changed")}]
        for row in rows:
            zone = ZONE_BY_PLACE.get((oblast, row.get("name")))
            if zone is None:
                _note_unknown(oblast, str(row.get("name")))
                continue
            states[zone.id] = ZoneState(
                zone_id=zone.id, name_uk=zone.name_uk, oblast=zone.oblast,
                alert=bool(row.get("alert")),
                changed_at=_parse_skog_time(row.get("changed")),
            )
    return states


def parse_aiu(payload: dict) -> dict[str, ZoneState]:
    """Active-alerts list -> {zone_id: state} for the ALERTING zones only.

    Deliberately not a full roster: this source reports what is on, and a zone
    it doesn't mention is only "not listed", which is not the same evidence as
    the roster source's dated «відбій». Returning quiet zones from here once
    meant an empty/broken payload read as "everything is clear" — the one
    direction this layer must never fail in.

    Only `air_raid` counts: shelling/urban-fighting alerts exist upstream but
    say nothing about the air situation this map is about.
    """
    rows = payload.get("raw")
    if not isinstance(rows, list):
        raise ValueError("active-alert payload has no 'raw' list")
    states: dict[str, ZoneState] = {}
    for row in rows:
        if row.get("alert_type") != "air_raid":
            continue
        oblast = row.get("location_oblast")
        title = row.get("location_title")
        zone = ZONE_BY_PLACE.get((oblast, title)) or ZONE_BY_PLACE.get((title, title))
        if zone is None:
            continue
        started = row.get("started_at")
        try:
            began = datetime.fromisoformat(started.replace("Z", "+00:00")) if started else None
        except (AttributeError, ValueError):
            began = None
        states[zone.id] = ZoneState(
            zone_id=zone.id, name_uk=zone.name_uk, oblast=zone.oblast,
            alert=True, changed_at=began,
        )
    return states


def apply_demo(states: dict[str, ZoneState], previous: dict[str, ZoneState],
               now: datetime | None = None) -> dict[str, ZoneState]:
    """Force `alert_zones_demo` zones to ALERT (dev only; no-op when unset).

    A forced zone keeps the instant it was first forced, so the tooltip counts
    up like a real siren instead of resetting to 0 every poll.
    """
    demo = settings.alert_zones_demo_list
    if not demo:
        return states
    now = now or utcnow()
    for zone_id in demo:
        base = states.get(zone_id)
        if base is None:
            log.warning("ALERT_ZONES_DEMO: unknown zone id %r", zone_id)
            continue
        held = previous.get(zone_id)
        began = held.changed_at if held is not None and held.alert else now
        states[zone_id] = replace(base, alert=True, changed_at=began)
    return states


def changed_zones(previous: dict[str, ZoneState],
                  current: dict[str, ZoneState]) -> list[ZoneState]:
    """Zones whose published state actually moved — the map only needs those."""
    return [s for zid, s in current.items() if previous.get(zid) != s]


def is_stale(now: datetime | None = None) -> bool:
    """Whether the last successful poll is too old to trust. True before the
    first one ever succeeds, so the layer starts out honestly unknown."""
    if _last_ok is None:
        return True
    now = now or utcnow()
    return (now - _last_ok).total_seconds() > settings.alert_zones_stale_after_s


def current_states() -> list[ZoneState]:
    """Every zone in roster order, so the client always gets all thirteen."""
    return [_states.get(z.id) or unknown_state(z) for z in ZONES]


def _zone_out(state: ZoneState, stale: bool) -> AlertZoneOut:
    return AlertZoneOut(
        zone_id=state.zone_id, name_uk=state.name_uk, oblast=state.oblast,
        alert=state.alert, changed_at=state.changed_at, stale=stale,
    )


def zones_out() -> list[AlertZoneOut]:
    stale = is_stale()
    return [_zone_out(s, stale) for s in current_states()]


async def _fetch(source: str) -> dict:
    url = f"{settings.alert_zones_url}?source={source}&raw"
    async with httpx.AsyncClient(timeout=settings.alert_zones_timeout_s) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


def merge_states(roster: dict[str, ZoneState],
                 active: dict[str, ZoneState]) -> dict[str, ZoneState]:
    """Union of two providers: a zone is under alert if EITHER says so.

    The two disagree in practice, and not symmetrically. Live 2026-08-19 23:06:
    alerts.in.ua had Вишгородський under an air raid that had been running 14
    minutes, while the roster source still reported відбій with its last
    transition six hours earlier — it had simply missed the alert. `stale`
    can't catch that: the provider was up and answering.

    So the merge is deliberately biased. On an air-raid map the two errors are
    not equal: showing a siren that has already ended is an annoyance, missing
    one that is sounding is the whole failure this layer exists to prevent.
    """
    merged = dict(roster)
    for zone_id, hot in active.items():
        if not hot.alert:
            continue
        base = merged.get(zone_id)
        if base is None or not base.alert:
            # Take the confirming source's start time too — the roster's
            # `changed_at` describes the clear it wrongly still believes in.
            merged[zone_id] = replace(hot, alert=True)
    return merged


async def poll_once(*, roster_only: bool = False) -> list[ZoneState]:
    """One poll of BOTH providers, merged. Returns the zones whose state
    changed (empty on a quiet minute). Raises only when NEITHER source yielded a
    watched zone — one of the two failing is survivable and merely logged."""
    global _states, _last_ok
    roster: dict[str, ZoneState] = {}
    active: dict[str, ZoneState] | None = None
    errors = []
    try:
        roster = parse_skog(await _fetch(settings.alert_zones_source))
    except Exception as ex:
        errors.append(f"{settings.alert_zones_source}: {ex}")
    if not roster_only:
        await asyncio.sleep(settings.alert_zones_source_gap_s)
        try:
            active = parse_aiu(await _fetch(settings.alert_zones_confirm_source))
        except Exception as ex:
            errors.append(f"{settings.alert_zones_confirm_source}: {ex}")

    if roster:
        parsed = merge_states(roster, active or {})
    elif active is not None:
        # Roster source down: the active-only source can still say WHICH zones
        # are alerting, it just can't date the quiet ones.
        parsed = {z.id: unknown_state(z) for z in ZONES} | active
    else:
        raise ValueError("no alert-zone provider returned a watched zone: "
                         + "; ".join(errors or ["empty payload"]))
    if errors:
        log.warning("alert zones: degraded, using one source (%s)", "; ".join(errors))

    parsed = apply_demo(parsed, _states)
    changed = changed_zones(_states, parsed)
    _states = parsed
    _last_ok = utcnow()
    return changed


async def _broadcast(states: list[ZoneState]) -> None:
    if not states:
        return
    stale = is_stale()
    await manager.broadcast(
        WSMessage(type="zones", zones=[_zone_out(s, stale) for s in states])
    )


async def run_alert_zones() -> None:
    """Poll forever, pushing only what changed."""
    failures = 0
    was_stale = True
    while True:
        try:
            changed = await poll_once()
            if failures:
                log.info("alert zones: provider recovered after %d failure(s)", failures)
            failures = 0
            if was_stale:
                # Coming back from an outage: republish everything, because the
                # client has been showing a greyed-out layer and doesn't know
                # which zones moved while we were blind.
                was_stale = False
                await _broadcast(current_states())
            else:
                await _broadcast(changed)
        except asyncio.CancelledError:
            raise
        except Exception as ex:
            failures += 1
            log.warning("alert-zone poll failed (%d in a row): %s", failures, ex)
            if not was_stale and is_stale():
                was_stale = True
                # Tell the map to grey out rather than keep showing a state we
                # can no longer vouch for.
                await _broadcast(current_states())
        await asyncio.sleep(settings.alert_zones_interval_s)


def reset_state() -> None:
    """Drop the in-memory snapshot (tests; process-global by design)."""
    global _states, _last_ok
    _states = {}
    _last_ok = None
    _unknown_places.clear()

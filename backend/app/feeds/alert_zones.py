"""Polls an external provider for the siren state of the watched raions and
pushes changes to the map.

The snapshot itself is in-memory only — see domain/alert_zones.py for why. What
survives a tick is the CONFIRMED transitions: `persist_once` debounces the
snapshot through domain/zone_alerts.py and reconciles it into `alerts` rows with
`scope='raion'`, which is what gives a reader outside Kyiv city a banner for
their own raion. The loop follows
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
from sqlalchemy import select

from ..api.ws import manager
from ..config import settings
from ..db import SessionLocal
from ..domain.alert_zones import (
    OBLAST_REGION,
    WATCHED_OBLASTS,
    ZONE_BY_ID,
    ZONE_BY_PLACE,
    ZONES,
    ZoneState,
    region_of,
    unknown_state,
)
from ..domain.alerts import AlertSignal, apply_alert_signal
from ..domain.zone_alerts import Pending, confirm_changes, signal_time
from ..models import Alert, utcnow
from ..pipeline.broadcast import broadcast_results
from ..pipeline.results import Broadcast
from ..schemas import AlertZoneOut, WSMessage
from ..timeutil import from_kyiv_local

log = logging.getLogger("alert_zones")

_SKOG_TIME = "%Y-%m-%d %H:%M:%S"
# The provider stamps "never observed a change" as the unix epoch in Kyiv time.
_EPOCH_YEAR = 1971

_states: dict[str, ZoneState] = {}
_last_ok: datetime | None = None
_unknown_places: set[tuple[str, str]] = set()
# Raion states waiting out the flicker guard — see domain/zone_alerts.py. Only
# the counter lives in memory; what has been COMMITTED is re-read from the DB
# every tick, so a restart mid-siren costs nothing.
_pending: dict[str, Pending] = {}


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


def latest_transition(payload: dict) -> datetime | None:
    """The most recent state change the ROSTER payload reports — anywhere in
    the country, not just in the watched oblasts.

    Nationwide on purpose: this is a liveness probe for the source, and our four
    oblasts can legitimately be quiet for hours while the rest of the country is
    not. Sentinel rows (the 2022 dates the provider carries for the occupied
    oblasts) lose the max and need no special case.
    """
    newest: datetime | None = None
    for entry in (payload.get("raw") or {}).values():
        rows = [entry, *(entry.get("districts") or [])]
        for row in rows:
            when = _parse_skog_time(row.get("changed"))
            if when is not None and (newest is None or when > newest):
                newest = when
    return newest


def latest_active_start(payload: dict) -> datetime | None:
    """The most recent air-raid START the ACTIVE payload reports, anywhere."""
    newest: datetime | None = None
    for row in payload.get("raw") or []:
        if row.get("alert_type") != "air_raid":
            continue
        started = row.get("started_at")
        try:
            when = datetime.fromisoformat(started.replace("Z", "+00:00")) if started else None
        except (AttributeError, ValueError):
            when = None
        if when is not None and (newest is None or when > newest):
            newest = when
    return newest


def roster_is_behind(roster_newest: datetime | None,
                     active_newest: datetime | None) -> bool:
    """Whether the roster source is demonstrably serving stale state.

    The failure this exists for, live on 2026-08-29: the roster source answered
    in milliseconds, with `cachedat` stamped the current second, and every
    transition in it dated 07:55 or earlier — a sixteen-hour-old snapshot in
    which Kyiv was still under a siren that had long ended. `is_stale()` cannot
    catch that; it measures when WE last polled, and we polled successfully
    every 20 seconds throughout.

    The signal is the two sources' own timestamps. While both are live they see
    the same transitions within seconds, so this gap is ~0 — including on a
    quiet night, when both simply report old news. It only opens when one stops
    receiving updates, and then it opens by hours.

    Deliberately one-directional: an ACTIVE source cannot tell us a zone went
    quiet (it lists only what is on), so it can never be judged behind this way,
    and this can never conclude "the roster is fine, the other one is stuck".
    """
    lag = settings.alert_zones_max_source_lag_s
    if lag <= 0 or roster_newest is None or active_newest is None:
        return False
    return (active_newest - roster_newest).total_seconds() > lag


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
    """Every zone in roster order, so the client always gets the whole roster."""
    return [_states.get(z.id) or unknown_state(z) for z in ZONES]


def _zone_out(state: ZoneState, stale: bool) -> AlertZoneOut:
    return AlertZoneOut(
        zone_id=state.zone_id, name_uk=state.name_uk, oblast=state.oblast,
        region=OBLAST_REGION[state.oblast],
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
    roster_newest: datetime | None = None
    active_newest: datetime | None = None
    errors = []
    try:
        payload = await _fetch(settings.alert_zones_source)
        roster = parse_skog(payload)
        roster_newest = latest_transition(payload)
    except Exception as ex:
        errors.append(f"{settings.alert_zones_source}: {ex}")
    if not roster_only:
        await asyncio.sleep(settings.alert_zones_source_gap_s)
        try:
            payload = await _fetch(settings.alert_zones_confirm_source)
            active = parse_aiu(payload)
            active_newest = latest_active_start(payload)
        except Exception as ex:
            errors.append(f"{settings.alert_zones_confirm_source}: {ex}")

    if roster and roster_is_behind(roster_newest, active_newest):
        # Discarded rather than merged. Merging would keep every siren it is
        # stuck on, because the merge can only ADD alerts — nothing downstream
        # can cancel one, so a stale roster's alerts would stand forever.
        # Dropping it falls through to the active-only branch below, which is
        # already the "roster unusable" path.
        log.warning(
            "alert zones: roster source is %.0f min behind the active one "
            "(newest transition %s vs %s) — dropping its state this tick",
            (active_newest - roster_newest).total_seconds() / 60,
            roster_newest, active_newest,
        )
        roster = {}

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


async def persist_once() -> list[Alert]:
    """Reconcile the current snapshot into `alerts` rows, debounced.

    Returns the alerts actually opened/closed this tick (empty on a quiet one).
    Nothing happens while the layer is `stale`: an unreachable provider tells us
    nothing about a raion, and treating its silence as an all-clear is the exact
    failure this layer is engineered against.
    """
    global _pending
    if is_stale():
        return []
    async with SessionLocal() as session:
        open_rows = list(await session.scalars(
            select(Alert).where(Alert.zone_id.is_not(None), Alert.ended_at.is_(None))
        ))
        committed = {a.zone_id: True for a in open_rows}
        observed = {s.zone_id: s for s in current_states()}
        _pending, confirmed = confirm_changes(
            _pending, committed, observed, settings.alert_zones_confirm_ticks
        )
        if not confirmed:
            return []
        now = utcnow()
        changed: list[Alert] = []
        for state in confirmed:
            zone = ZONE_BY_ID[state.zone_id]
            alert = await apply_alert_signal(session, AlertSignal(
                scope="raion",
                action="start" if state.alert else "end",
                when=signal_time(state, now),
                region=region_of(zone),
                provider=settings.alert_zones_source,
                zone_id=zone.id,
            ))
            if alert is not None:
                changed.append(alert)
        if changed:
            await broadcast_results(session, [Broadcast("alert", alert=a) for a in changed])
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
            if settings.alert_zones_persist:
                # Guarded separately: the map layer is the job this loop must
                # never lose, and a DB hiccup writing raion alerts is not a
                # reason to stop painting sirens.
                try:
                    await persist_once()
                except Exception as ex:
                    log.warning("alert zones: persisting raion alerts failed: %s", ex)
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
    global _states, _last_ok, _pending
    _states = {}
    _last_ok = None
    _pending = {}
    _unknown_places.clear()

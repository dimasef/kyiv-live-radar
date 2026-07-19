"""Web Push for danger-near-home.

Hooked into broadcast_results' threat branch (the single fan-out point, already
outside the ingest lock): every broadcast track is assessed against each stored
subscription's home zone (app/domain/home_danger.py) and a push fires ONLY on a
level escalation — none->warning, none->danger, warning->danger — deduped per
(subscription, track) via PushSubscription.danger_state, with a cooldown so an
oscillating level can't machine-gun re-pushes.

Policy (see .claude/plans/home-danger.md): the wording is SUPPLEMENTARY —
«Допоміжно:» prefix, never «Повітряна тривога», always framed as volunteer
data. TTL is short so a stale danger push dies in transit instead of arriving
minutes after the situation moved on.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from ..config import settings
from ..domain.geometry import haversine_km
from ..domain.home_danger import DangerLevel, HomeZone, assess
from ..models import PushSubscription, Threat, utcnow
from ..timeutil import naive

log = logging.getLogger("home_push")

PUSH_TTL_S = 300

_TYPE_LABEL = {
    "shahed": "Шахед",
    "jet_drone": "Реактивний БпЛА",
    "missile": "Ракета",
    "ballistic": "Балістика",
    "unknown": "Ціль",
}

_TITLES = {
    DangerLevel.WARNING: "⚠️ Увага: курс у бік вашої зони",
    DangerLevel.DANGER: "‼️ Увага: ціль поруч із вашою зоною",
}


def _sub_prefs(sub: PushSubscription) -> tuple[DangerLevel, set[str], bool]:
    """Normalize a subscription's stored prefs — the single place absent keys
    get their permissive defaults (warning floor, all types, citywide on).
    `unknown` targets always pass the type filter: an untyped track can still
    be the most dangerous thing in the sky, and filtering it out silently is
    the one mistake this feature must not make."""
    prefs = sub.prefs or {}
    min_level = DangerLevel.DANGER if prefs.get("min_level") == "danger" else DangerLevel.WARNING
    types = set(prefs.get("types") or ("ballistic", "missile", "shahed", "jet_drone"))
    types.add("unknown")
    return min_level, types, bool(prefs.get("citywide", True))


async def evaluate_home_danger(session, threat: Threat) -> None:
    """Assess one broadcast track against every subscription's home zone and
    push on escalation. Requires threat.events with districts eager-loaded
    (broadcast_results' _load_full already does)."""
    if not (settings.home_danger_enabled and settings.push_configured):
        return
    if threat.scope == "city":
        await _evaluate_citywide(session, threat)
        return
    subs = list(await session.scalars(select(PushSubscription)))
    any_changed = False
    for sub in subs:
        if sub.home_lat is None or sub.home_lon is None:
            continue
        min_level, allowed_types, _ = _sub_prefs(sub)
        if threat.target_type not in allowed_types:
            continue
        home = HomeZone(
            lat=sub.home_lat,
            lon=sub.home_lon,
            radius_km=sub.home_radius_km,
            raion_district_ids=tuple(sub.home_district_ids or ()),
        )
        level = assess(threat, home)
        key = str(threat.id)
        prev = sub.danger_state.get(key, {})
        prev_level = prev.get("level", 0)
        max_pushed = prev.get("max_pushed", 0)
        changed = False

        if threat.closed_at is not None:
            # Track over — prune its bookkeeping so danger_state doesn't grow
            # forever (and, after a reprocess reuses ids, doesn't suppress an
            # unrelated new track).
            if key in sub.danger_state:
                del sub.danger_state[key]
                changed = True
        else:
            should_push = (
                level >= min_level  # the sub's escalation floor ("тільки небезпека")
                and level > prev_level
                and (level > max_pushed or _cooldown_passed(prev.get("pushed_at")))
            )
            if should_push:
                payload = build_payload(level, threat, home)
                await _send(session, sub, payload)
                sub.last_push_at = utcnow()
                sub.danger_state[key] = {
                    "level": int(level),
                    "max_pushed": max(max_pushed, int(level)),
                    "pushed_at": utcnow().isoformat(),
                }
                changed = True
            elif level != prev_level:
                sub.danger_state[key] = {
                    "level": int(level),
                    "max_pushed": max_pushed,
                    "pushed_at": prev.get("pushed_at"),
                }
                changed = True

        if changed:
            flag_modified(sub, "danger_state")
            any_changed = True
    if any_changed:
        await session.commit()


def _cooldown_passed(pushed_at_iso: str | None) -> bool:
    if not pushed_at_iso:
        return True
    pushed_at = datetime.fromisoformat(pushed_at_iso)
    return utcnow() - pushed_at > timedelta(minutes=settings.home_push_cooldown_minutes)


def build_payload(level: DangerLevel, threat: Threat, home: HomeZone) -> dict:
    head = _head_event(threat)
    label = _TYPE_LABEL.get(threat.target_type, _TYPE_LABEL["unknown"])
    where = f" ({head.district.name_uk})" if head is not None else ""
    if threat.target_type == "ballistic":
        # No km figure for ballistic: the trigger is usually the raion callout,
        # and a centroid distance next to «ціль поруч» reads as contradiction.
        approx = " близько"
    elif head is not None:
        km = round(haversine_km(head.district.lat, head.district.lon, home.lat, home.lon))
        approx = f" ~{km} км від дому" if km > 0 else " у вашій зоні"
    else:
        approx = ""
    return {
        "kind": "home-danger",
        "level": "danger" if level == DangerLevel.DANGER else "warning",
        "threat_id": threat.id,
        "tag": f"klr-home-{threat.id}",
        "title": _TITLES[level],
        "body": f"{label}{approx}{where}. Волонтерські дані — не офіційна тривога.",
        "url": "/",
    }


async def _evaluate_citywide(session, threat: Threat) -> None:
    """Push once per city-wide alert track to every subscription that opted in
    («загроза по всьому місту»). No zone geometry — the whole city is the zone;
    a home is not even required. Deduped per (subscription, track) via the same
    danger_state bookkeeping (key "city:<id>"), so the grace-period reopen of a
    stood-down alert does NOT re-push; a genuinely new salvo has a new track."""
    subs = list(await session.scalars(select(PushSubscription)))
    any_changed = False
    for sub in subs:
        _, allowed_types, citywide_on = _sub_prefs(sub)
        key = f"city:{threat.id}"
        changed = False
        if threat.closed_at is not None:
            if key in sub.danger_state:
                del sub.danger_state[key]
                changed = True
        elif (
            citywide_on
            and threat.target_type in allowed_types
            and key not in sub.danger_state
            # Own cooldown against the previous CITYWIDE push only — a recent
            # home push must never swallow the city-level signal.
            and _cooldown_passed(sub.danger_state.get("city_last_push"))
        ):
            label = _TYPE_LABEL.get(threat.target_type, _TYPE_LABEL["unknown"])
            await _send(session, sub, {
                "kind": "citywide",
                "level": "danger",
                "threat_id": threat.id,
                "tag": f"klr-city-{threat.id}",
                "title": f"‼️ Загроза по всьому місту: {label.lower()}",
                "body": "Допоміжно: ціль на Київ без прив'язки до району. "
                        "Волонтерські дані — не офіційна тривога.",
                "url": "/",
            })
            sub.last_push_at = utcnow()
            sub.danger_state[key] = {"pushed_at": utcnow().isoformat()}
            sub.danger_state["city_last_push"] = utcnow().isoformat()
            changed = True
        if changed:
            flag_modified(sub, "danger_state")
            any_changed = True
    if any_changed:
        await session.commit()


def _head_event(threat: Threat):
    located = [ev for ev in threat.events if ev.district is not None]
    # naive(): a live track mixes DB-loaded (naive) and just-added (aware)
    # event times — a raw max() across the two raises TypeError.
    return max(located, key=lambda ev: naive(ev.event_time)) if located else None


async def _send(session, sub: PushSubscription, payload: dict) -> None:
    from pywebpush import WebPushException, webpush  # deferred: optional at import time

    try:
        # webpush() is synchronous (requests under the hood) — never block the
        # event loop with it.
        await asyncio.to_thread(
            webpush,
            subscription_info={
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
            },
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_subject},
            ttl=PUSH_TTL_S,
        )
    except WebPushException as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status in (404, 410):
            # The push service says this endpoint is gone (browser unsubscribed
            # or the registration expired) — drop the row.
            log.info("push endpoint gone (%s), deleting subscription %s", status, sub.id)
            await session.delete(sub)
        else:
            log.warning("web push failed (status=%s): %s", status, e)

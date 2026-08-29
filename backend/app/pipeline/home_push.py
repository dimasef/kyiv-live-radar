"""Web Push for danger-near-home.

Hooked into broadcast_results' threat branch (the single fan-out point, already
outside the ingest lock): every broadcast track is assessed against each stored
subscription's home zone (app/domain/home_danger.py) and a push fires ONLY on a
level escalation — none->warning, none->danger, warning->danger — deduped per
(subscription, track) via PushSubscription.danger_state, with a cooldown so an
oscillating level can't machine-gun re-pushes.

`evaluate_regional_ballistic` is the fourth path, off the NOTICE branch of the
same fan-out: a ballistic threat stated for a whole oblast never becomes a track,
so nothing above can see it. See its own comment for why that is the shape
outside Kyiv.

Policy (see .claude/plans/home-danger.md): the wording is SUPPLEMENTARY —
«Допоміжно:» prefix, never «Повітряна тривога», always framed as volunteer
data. TTL is short so a stale danger push dies in transit instead of arriving
minutes after the situation moved on.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from ..config import settings
from ..domain.geometry import haversine_km
from ..domain.home_danger import DangerLevel, HomeZone, assess
from ..domain.origins import ORIGIN_BY_KEY
from ..models import HOME_REGION, Notice, PushSubscription, Threat, utcnow
from ..parsing.matcher import normalize
from ..parsing.vocab import _LEVEL_AHEAD_RE
from ..regions import label as region_label
from ..timeutil import naive
from .webpush import send_push

log = logging.getLogger("home_push")

# The label a push says out loud («‼️ Шахед поруч із домом»). It must match what
# the type MEANS, and `shahed` is the generic drone bucket — «дрон», «бпла»,
# «баражуюч», Ланцет, Італмас and Гербера all land in it — not the Shahed-136.
# This was the only surface still naming the model: the map, the feed and the
# admin badge have all said «БПЛА» throughout, so a bare «БпЛА» callout has been
# pushing as «Шахед» since the feature shipped.
_TYPE_LABEL = {
    "shahed": "БпЛА",
    "jet_drone": "Реактивний БпЛА",
    "fpv": "FPV",
    "kab": "КАБ",
    "missile": "Ракета",
    "ballistic": "Балістика",
    "unknown": "Ціль",
}


def _sub_prefs(sub: PushSubscription) -> tuple[DangerLevel, set[str], bool]:
    """Normalize a subscription's stored prefs — the single place absent keys
    get their permissive defaults (warning floor, all types, citywide on).
    `unknown` targets always pass the type filter: an untyped track can still
    be the most dangerous thing in the sky, and filtering it out silently is
    the one mistake this feature must not make."""
    prefs = sub.prefs or {}
    min_level = DangerLevel.DANGER if prefs.get("min_level") == "danger" else DangerLevel.WARNING
    types = set(
        prefs.get("types") or ("ballistic", "missile", "kab", "shahed", "jet_drone", "fpv")
    )
    types.add("unknown")
    return min_level, types, bool(prefs.get("citywide", True))


def _danger_state(sub: PushSubscription) -> dict:
    """The subscription's per-track bookkeeping, materialized if absent.

    The column is nullable and legacy rows carry SQL NULL, which every `.get`
    and `in` below would turn into an AttributeError — inside the push fan-out,
    where it would take down the notification for everyone in the same batch.
    Assigning the default back onto `sub` keeps subsequent mutations tracked."""
    if sub.danger_state is None:
        sub.danger_state = {}
    return sub.danger_state


async def evaluate_home_danger(session, threat: Threat) -> None:
    """Assess one broadcast track against every subscription's home zone and
    push on escalation. Requires threat.events with districts eager-loaded
    (broadcast_results' _load_full already does)."""
    if not (settings.home_danger_enabled and settings.push_configured):
        return
    if threat.scope == "city":
        await _evaluate_citywide(session, threat)
        return
    # Only subscriptions that have a home can be assessed against one, and only
    # those following THIS track's region — a device in Kharkiv is not woken by
    # a Kyiv track and vice versa. Both filters in SQL rather than loading every
    # row and skipping most of them.
    #
    # The region gate used to be a single `threat.region != HOME_REGION` return
    # at the top. It cannot be: the region is a property of the DEVICE now, not
    # of the deployment, so it has to be asked per subscription. NULL means the
    # home region, which is what every row predating the column was.
    #
    # It stays an explicit gate rather than being left to the distance math even
    # though a far-away track would measure "safe" anyway — this is a phone
    # waking someone at 3am.
    subs = list(
        await session.scalars(
            select(PushSubscription).where(
                PushSubscription.home_lat.is_not(None),
                PushSubscription.home_lon.is_not(None),
                _follows_region(threat.region),
            )
        )
    )
    any_changed = False
    for sub in subs:
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
        state = _danger_state(sub)
        prev = state.get(key, {})
        prev_level = prev.get("level", 0)
        max_pushed = prev.get("max_pushed", 0)
        changed = False

        if threat.closed_at is not None:
            # Track over — prune its bookkeeping so danger_state doesn't grow
            # forever (and, after a reprocess reuses ids, doesn't suppress an
            # unrelated new track).
            if key in state:
                del state[key]
                changed = True
        else:
            should_push = (
                level >= min_level  # the sub's escalation floor ("тільки небезпека")
                and level > prev_level
                and (level > max_pushed or _cooldown_passed(prev.get("pushed_at")))
            )
            if should_push:
                payload = build_payload(level, threat, home)
                await send_push(session, sub, payload)
                sub.last_push_at = utcnow()
                state[key] = {
                    "level": int(level),
                    "max_pushed": max(max_pushed, int(level)),
                    "pushed_at": utcnow().isoformat(),
                }
                changed = True
            elif level != prev_level:
                state[key] = {
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
    # Type leads the TITLE so it reads at a glance on a lock screen — the body
    # then carries only WHERE/how close.
    title = (
        f"⚠️ {label} прямує у ваш бік"
        if level == DangerLevel.WARNING
        else f"‼️ {label} поруч із домом"
    )
    where = head.district.name_uk if head is not None else None
    if threat.target_type == "ballistic":
        # No km figure for ballistic: the trigger is usually the raion callout,
        # and a centroid distance next to «поруч» reads as a contradiction.
        loc = where or ""
    elif head is not None:
        km = round(haversine_km(head.district.lat, head.district.lon, home.lat, home.lon))
        loc = f"~{km} км від дому ({where})" if km > 0 else f"у вашій зоні ({where})"
    else:
        loc = ""
    body = f"{loc}. " if loc else ""
    return {
        "kind": "home-danger",
        "level": "danger" if level == DangerLevel.DANGER else "warning",
        "threat_id": threat.id,
        "tag": f"klr-home-{threat.id}",
        "title": title,
        "body": f"{body}Волонтерські дані — не офіційна тривога.",
        "url": "/",
    }


def _follows_region(region: str):
    """SQL predicate: this subscription wants `region`'s tracks.

    NULL on the column means the deployment's home region — the implicit value
    of every row written before devices could travel."""
    if region == HOME_REGION:
        return sa.or_(PushSubscription.region.is_(None), PushSubscription.region == region)
    return PushSubscription.region == region


async def _evaluate_citywide(session, threat: Threat) -> None:
    """Push once per city-wide alert track to every subscription that opted in
    («загроза по всьому місту»). No zone geometry — the whole city is the zone;
    a home is not even required. Deduped per (subscription, track) via the same
    danger_state bookkeeping (key "city:<id>"), so the grace-period reopen of a
    stood-down alert does NOT re-push; a genuinely new salvo has a new track."""
    # City-wide tracks are forced to the home region on creation (see
    # ingest/handlers), so this is «загроза по всьому місту» for the home city
    # only — a device following another region must not be woken by it.
    subs = list(
        await session.scalars(select(PushSubscription).where(_follows_region(threat.region)))
    )
    any_changed = False
    for sub in subs:
        _, allowed_types, citywide_on = _sub_prefs(sub)
        state = _danger_state(sub)
        key = f"city:{threat.id}"
        changed = False
        if threat.closed_at is not None:
            if key in state:
                del state[key]
                changed = True
        elif (
            citywide_on
            and threat.target_type in allowed_types
            and key not in state
            # Own cooldown against the previous CITYWIDE push only — a recent
            # home push must never swallow the city-level signal.
            and _cooldown_passed(state.get("city_last_push"))
        ):
            label = _TYPE_LABEL.get(threat.target_type, _TYPE_LABEL["unknown"])
            await send_push(session, sub, {
                "kind": "citywide",
                "level": "danger",
                "threat_id": threat.id,
                "tag": f"klr-city-{threat.id}",
                "title": f"‼️ {label} — загроза по всьому місту",
                "body": "Ціль на Київ без прив'язки до району. "
                        "Волонтерські дані — не офіційна тривога.",
                "url": "/",
            })
            sub.last_push_at = utcnow()
            state[key] = {"pushed_at": utcnow().isoformat()}
            state["city_last_push"] = utcnow().isoformat()
            changed = True
        if changed:
            flag_modified(sub, "danger_state")
            any_changed = True
    if any_changed:
        await session.commit()


# Ballistic threat stated for a whole oblast, with no place in it to put on the
# map. Kyiv is the only region whose ballistic callouts name a RAION — 14 of its
# 500 stored ballistic messages do («🚀 Балістика по Подільському району!»), and
# that is the shape HomeZone.raion_district_ids and assess() were built for.
# The northern channels never do: all 28 stored ballistic messages from Sumy and
# Chernihiv are an oblast-wide threat naming a launch ORIGIN («Загроза балістики
# з Курська») and, later, «Відбій загрози балістики». Naming no place, they never
# reach the tracking layer at all — they surface as a forecast/directional
# NOTICE, so the raion escalation has nothing to fire on and silently never runs.
#
# Outside the raion-mapped area, then, the oblast is the zone. This is the same
# escalation one administrative level up, and it deliberately fires ONLY where
# the raion one cannot: a home that resolved to raion ids (i.e. inside Kyiv city,
# the only place `boundaries.json` covers) keeps exactly today's behaviour and is
# never woken by this. A home with no zone at all gets nothing either — the whole
# subsystem is home-based, and `citywide` is the one opt-in path that isn't.
#
# Level is WARNING, not DANGER: the statement is true of the entire oblast, so
# «поруч із домом» would be a lie. It respects the subscription's floor, which
# makes "тільки небезпека" the natural opt-out.
_REGIONAL_BALLISTIC_KINDS = ("directional", "forecast")

# How long one oblast-level threat stays "the same episode" without an explicit
# відбій. The Sumy channels do send one (5 clears against 2 opens in the corpus);
# the Chernihiv one never has (0 against 6), so without an expiry its key would
# pin the state forever and swallow the next night's threat.
_REGIONAL_BALLISTIC_TTL = timedelta(hours=3)


async def evaluate_regional_ballistic(session, notice: Notice) -> None:
    """Push an oblast-wide ballistic warning off a threat-level notice.

    Hooked into broadcast_results' notice branch. Unlike `assess`, this has no
    frontend twin: there is no geometry to draw, and the notice itself already
    appears in the feed.
    """
    if not (settings.home_danger_enabled and settings.push_configured):
        return
    if notice.target_type != "ballistic":
        return
    region = (notice.source.region if notice.source else None) or HOME_REGION
    if notice.kind == "clear":
        await _clear_regional_ballistic(session, region)
        return
    if notice.kind not in _REGIONAL_BALLISTIC_KINDS:
        return
    # «Найближчим часом можлива повторна хвиля балістики» is about what MIGHT
    # come, not what is in the sky — the same distinction ingest/context.py draws
    # before it lets a message set a channel's type context. It also covers the
    # continuation phrasing («поки ще діє балістична загроза»), which must not
    # re-push a threat that already did.
    if _LEVEL_AHEAD_RE.search(normalize(notice.text)):
        return

    key = f"balreg:{region}"
    subs = list(
        await session.scalars(
            select(PushSubscription).where(
                PushSubscription.home_lat.is_not(None),
                PushSubscription.home_lon.is_not(None),
                _follows_region(region),
            )
        )
    )
    any_changed = False
    for sub in subs:
        # The gate that keeps Kyiv exactly as it is: a home the raion escalation
        # can serve is not served twice.
        if sub.home_district_ids:
            continue
        min_level, allowed_types, _ = _sub_prefs(sub)
        if "ballistic" not in allowed_types or min_level > DangerLevel.WARNING:
            continue
        state = _danger_state(sub)
        if not _episode_over(state.get(key)):
            continue
        await send_push(session, sub, _regional_ballistic_payload(region, notice))
        sub.last_push_at = utcnow()
        state[key] = {"pushed_at": utcnow().isoformat()}
        flag_modified(sub, "danger_state")
        any_changed = True
    if any_changed:
        await session.commit()


def _episode_over(entry: dict | None) -> bool:
    """True when nothing was pushed for this oblast recently enough to still be
    the same threat — i.e. a new push is a new escalation, not a repeat."""
    if not entry or not entry.get("pushed_at"):
        return True
    return utcnow() - datetime.fromisoformat(entry["pushed_at"]) > _REGIONAL_BALLISTIC_TTL


def _regional_ballistic_payload(region: str, notice: Notice) -> dict:
    """Both names are stated in the NOMINATIVE after a full stop rather than
    inflected into the sentence. «по Сумщині» and «з Курщини» would each need a
    different case, and deriving one from a display string is a trap the first
    region not ending in «-щина» springs."""
    origin = ORIGIN_BY_KEY.get(notice.origin or "")
    whence = f" Напрямок пуску: {origin.name_uk}." if origin else ""
    return {
        "kind": "regional-ballistic",
        "level": "warning",
        "tag": f"klr-balreg-{region}",
        "title": "⚠️ Балістика — загроза по області",
        "body": f"{region_label(region)}.{whence} "
                "Волонтерські дані — не офіційна тривога.",
        "url": "/",
    }


async def _clear_regional_ballistic(session, region: str) -> None:
    """«Відбій загрози балістики» ends the episode, so the next threat over the
    same oblast pushes again instead of being deduped against a stale key."""
    key = f"balreg:{region}"
    subs = list(await session.scalars(select(PushSubscription).where(_follows_region(region))))
    any_changed = False
    for sub in subs:
        state = _danger_state(sub)
        if key in state:
            del state[key]
            flag_modified(sub, "danger_state")
            any_changed = True
    if any_changed:
        await session.commit()


def _head_event(threat: Threat):
    located = [ev for ev in threat.events if ev.district is not None]
    # naive(): a live track mixes DB-loaded (naive) and just-added (aware)
    # event times — a raw max() across the two raises TypeError.
    return max(located, key=lambda ev: naive(ev.event_time)) if located else None

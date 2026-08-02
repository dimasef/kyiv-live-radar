"""Per-message handlers + the `_dispatch` table — the tracking half of the
pipeline (track / notice / axis / impact / clear). Each handler takes an
IngestContext and returns its broadcasts; `_dispatch` picks exactly one in fixed
precedence order. No triage/LLM here."""

from __future__ import annotations

import logging

from sqlalchemy import select

from ...config import settings
from ...domain.axes import AxisSignal, apply_axis_signal, refresh_open_axis
from ...domain.districts import citywide_district_id
from ...domain.incidents import (
    attach_to_incident,
    end_active_incidents,
    end_incidents_without_open_tracks,
)
from ...domain.lifecycle import close_track, reopen_track
from ...domain.tracking import (
    apply_fusion,
    close_all_active,
    find_corroborating_track,
    find_open_citywide,
    find_open_track,
    find_recent_impact,
    find_stood_down_citywide,
    find_stood_down_track,
    find_track_by_reply,
)
from ...models import Alert, Notice, Threat, ThreatEvent
from ...parsing import DistrictHit, ParseResult
from ..results import Broadcast
from .context import IngestContext, _apply_update, _new_track, _upgrade_type

log = logging.getLogger("tracking")


def _axis_dedup_key(ctx: IngestContext) -> str:
    """Independent-source identity for axis corroboration (see
    fusion._origin_keys / triage._source_dedup_key)."""
    if ctx.forwarded_from_channel_id is not None:
        return f"orig:{ctx.forwarded_from_channel_id}"
    return f"src:{ctx.source_id}"


async def _raise_axis_from_parsed(ctx: IngestContext) -> Broadcast | None:
    """Raise/refresh a directional axis for a message that named an inbound
    origin (ctx.parsed.origin_key/_sector), whether it stood alone (directional)
    or accompanied a city/district sighting. No-op when no origin was named."""
    parsed = ctx.parsed
    if parsed.origin_sector is None:
        return None
    axis = await apply_axis_signal(ctx.session, AxisSignal(
        sector=parsed.origin_sector,
        target_type=parsed.target_type,
        when=ctx.when,
        origin_key=parsed.origin_key,
        source_dedup_key=_axis_dedup_key(ctx),
        raw_id=ctx.raw.id,
    ))
    return Broadcast("axis", axis=axis) if axis is not None else None


async def _incident_broadcast(ctx: IngestContext, track: Threat) -> Broadcast:
    """Attach `track` to the live incident and wrap it as an 'attack' broadcast —
    folds the repeated decoy/hypersonic threading into one place."""
    inc = await attach_to_incident(ctx.session, track, ctx.when,
                                   decoy=ctx.parsed.decoy, hypersonic=ctx.parsed.hypersonic)
    return Broadcast("attack", incident=inc)


async def _append_axis(ctx: IngestContext, broadcasts: list[Broadcast]) -> None:
    """Append a directional-axis broadcast if this message named an inbound
    origin (no-op otherwise)."""
    axis_bc = await _raise_axis_from_parsed(ctx)
    if axis_bc is not None:
        broadcasts.append(axis_bc)


async def _handle_directional(ctx: IngestContext) -> list[Broadcast]:
    """Standalone directional/origin callout ("Загроза балістики з Брянська") —
    no Kyiv raion to localize. Raise a directional AXIS (a screen-edge wedge)
    and surface a rule-generated directional notice in the feed; never a track."""
    parsed, when = ctx.parsed, ctx.when
    notice = Notice(
        kind="directional", text=parsed.raw_text, target_type=parsed.target_type,
        source_id=ctx.source_id, event_time=when, source_message_id=ctx.message_id,
        origin=parsed.origin_key, generated_by="rule",
    )
    ctx.session.add(notice)
    await ctx.session.commit()
    axis_bc = await _raise_axis_from_parsed(ctx)
    await ctx.done()
    broadcasts: list[Broadcast] = [Broadcast("notice", notice=notice)]
    if axis_bc is not None:
        broadcasts.append(axis_bc)
    return broadcasts


async def _handle_clear(ctx: IngestContext) -> list[Broadcast]:
    """All-clear closes every open track — or, if clear_scope is set (a
    ballistic-only stand-down, "Відбій балістичної загрози з Криму"), only
    open tracks of that type, so an unrelated active shahed/jet track isn't
    incorrectly closed by a clear that never mentioned it."""
    session, parsed, when = ctx.session, ctx.parsed, ctx.when
    closed = await close_all_active(session, when, "all_clear", target_type=parsed.clear_scope)
    # A FULL all-clear ("Відбій тривоги") ends the attack — close its
    # incident too. A type-scoped clear ("Відбій балістики") ends an incident
    # only when it leaves NO open tracks: with the scoped type stood down and
    # nothing else flying, a still-"active" attack (banner + raion highlight)
    # reads as a bug; an open track of another type keeps it active.
    if parsed.clear_scope is None:
        ended = await end_active_incidents(session, when, "all_clear")
    else:
        ended = await end_incidents_without_open_tracks(session, when, "all_clear")
    # Surface the all-clear itself in the feed (a status-only broadcast is
    # invisible there) as a notice — the operator wants to SEE "відбій".
    notice = await _make_notice(session, "clear", parsed, ctx.source_id, when, ctx.message_id)
    await ctx.done()
    return (
        [Broadcast("status", t) for t in closed]
        + [Broadcast("attack", incident=inc) for inc in ended]
        + [Broadcast("notice", notice=notice)]
    )


async def _handle_lost_signal(ctx: IngestContext) -> list[Broadcast]:
    """"Дорозвідка" — ППО temporarily has no targets of the stated type (or,
    if unstated, none at all): a real stand-down signal, not a confirmed
    all-clear. Type-scoped when a type is named, else every open track. Each
    closed track gets its own event (inheriting that track's last known
    district) so the message is visible in the feed/track-inspect view
    instead of vanishing as a bare status broadcast."""
    session, parsed, when = ctx.session, ctx.parsed, ctx.when
    target = parsed.target_type if parsed.target_type != "unknown" else None
    closed = await close_all_active(session, when, "stand_down", target_type=target)
    pairs: list[tuple[Threat, ThreatEvent | None]] = []
    for t in closed:
        hit = _last_district_hit(t)
        ev = None
        if hit is not None:
            ev = _make_event(ctx, t.id, hit, target_count=t.target_count)
            session.add(ev)
        pairs.append((t, ev))
    if any(ev is not None for _, ev in pairs):
        await session.commit()
        for t, ev in pairs:
            if ev is not None:
                await apply_fusion(session, t)
    # A stand-down that leaves no open tracks ends the attack too — same
    # rationale as the type-scoped clear in _handle_clear above.
    ended = await end_incidents_without_open_tracks(session, when, "all_clear")
    await ctx.done()
    return [Broadcast("event" if ev is not None else "status", t, ev) for t, ev in pairs] + [
        Broadcast("attack", incident=inc) for inc in ended
    ]


async def _pulse_corroborates_axis(ctx: IngestContext) -> list[Broadcast] | None:
    """Fallback for a terse pulse when NO city-wide alert is open: if a
    directional axis is still open ("Загроза балістики з Брянська" → wedge),
    "Є вихід" is the spotter calling in the launch that axis warned about.
    Freshen the axis (keep the wedge alive) and surface the pulse as a
    directional notice inheriting the axis's origin/type, so it folds into that
    direction's feed card instead of being dropped as "не про загрозу". Returns
    None (still unhandled) when no axis matches — caller falls through."""
    session, parsed, when = ctx.session, ctx.parsed, ctx.when
    axis = await refresh_open_axis(session, when, parsed.target_type, raw_id=ctx.raw.id)
    if axis is None:
        return None
    notice = Notice(
        kind="directional", text=parsed.raw_text, target_type=axis.target_type,
        source_id=ctx.source_id, event_time=when, source_message_id=ctx.message_id,
        origin=axis.origin_key, generated_by="rule",
    )
    session.add(notice)
    await session.commit()
    await ctx.done()
    return [Broadcast("notice", notice=notice), Broadcast("axis", axis=axis)]


async def _handle_target_pulse(ctx: IngestContext) -> list[Broadcast] | None:
    """Terse target/launch pulse ("Ціль!", "Ще вихід", "3 ракети") — acted on
    while a city-wide alert is already open: a spotter calling the salvo in as
    it arrives. It corroborates that alert (an event on the sentinel district)
    and bumps the stated count. With no open city-wide alert it falls back to
    corroborating an open directional axis (_pulse_corroborates_axis); only if
    neither is open does it return None (too terse to localize on its own) and
    the caller falls through to the next check."""
    session, parsed, when = ctx.session, ctx.parsed, ctx.when
    city = await find_open_citywide(session, when)
    if city is None:
        stood = await find_stood_down_citywide(session, when)
        if stood is not None:
            city = reopen_track(stood)
    if city is None and parsed.target_type != "unknown" and await _city_alert_open(session):
        # A TYPED pulse while the official siren is already sounding is the
        # first — and for a hypersonic the only — warning we get. Live
        # 2026-08-01: "Циркон" landed 24 s after the КМДА alert but 12 s before
        # anything opened a city-wide track, so it fell through to "без району";
        # the identical message 36 s later corroborated fine. Losing the
        # earliest ballistic callout to a seconds-wide race is the opposite of
        # what this handler is for, so a typed one opens the track itself.
        return await _handle_citywide(ctx)
    did = await citywide_district_id(session) if city is not None else None
    if city is None or did is None:
        return await _pulse_corroborates_axis(ctx)
    # A pulse corroborates the city alert but never promotes it (too terse).
    _apply_update(parsed, city, promote=False)
    ev = _make_event(ctx, city.id, DistrictHit(did, "", 0), target_count=city.target_count)
    session.add(ev)
    await session.commit()
    await apply_fusion(session, city)
    attack_bc = await _incident_broadcast(ctx, city)
    await ctx.done()
    return [Broadcast("event", city, ev), attack_bc]


async def _handle_summary(ctx: IngestContext) -> list[Broadcast]:
    """Retrospective attack summary ("Загалом ... 8 балістичних С-400") — info,
    not a live target: no map threat, but surfaced in the feed as a notice so
    the operator sees the tally of the attack."""
    notice = await _make_notice(ctx.session, "summary", ctx.parsed, ctx.source_id, ctx.when,
                                ctx.message_id)
    await ctx.done()
    return [Broadcast("notice", notice=notice)]


async def _handle_destroyed(ctx: IngestContext) -> list[Broadcast]:
    """Destroyed closes the matching open track. A "Мінус"-style reply names
    its target's chain directly; otherwise prefer the track over the named
    district, not merely the newest (see find_open_track)."""
    session, parsed, when = ctx.session, ctx.parsed, ctx.when
    track = await find_track_by_reply(session, ctx.source_id, ctx.reply_to_message_id)
    if track is None:
        prefer = {h.district_id for h in parsed.districts} or None
        # A destroyed message can land later than the normal grouping gap
        # (track_gap_minutes) but before the track would otherwise go
        # stale — look as far back as the stale window, not the grouping
        # window, so a reply-less "знищено" in that gap still finds its
        # track instead of silently matching nothing.
        track = await find_open_track(
            session, when, prefer_districts=prefer, gap_minutes=settings.track_stale_minutes
        )
    if track is None:
        await ctx.done()
        return []
    # A partial interception ("По ракетам мінус", "збито") must NOT close a
    # CITY-WIDE alert: scope='city' represents an ongoing city-level barrage
    # (10 S-400 over 20 min), not one trackable target. Closing it on the first
    # "мінус" split one barrage into two citywide tracks — the next "на місто"
    # callout couldn't rejoin the just-closed alert and spawned a second one
    # (live 2026-07-15: tracks 238+239). Only a real відбій (all_clear) or the
    # stale sweeper ends a city-wide alert; a мінус here is an informational
    # echo we drop rather than act on.
    if track.scope == "city":
        await ctx.done()
        return []
    # A closing message often names no district of its own ("Один збили,
    # залишився ще один") — inherit the track's last known position so the
    # message still becomes a real event (visible in the feed and in a
    # track's inspect view), instead of silently vanishing with only a
    # status-only broadcast the feed never displays.
    hit = parsed.districts[0] if parsed.districts else _last_district_hit(track)
    ev = None
    if hit is not None:
        ev = _make_event(ctx, track.id, hit, target_count=track.target_count)
        session.add(ev)
    close_track(track, when, "destroyed")
    await session.commit()
    await apply_fusion(session, track)
    await ctx.done()
    # "event" (not "status") whenever we actually created one, so the
    # frontend feed (which only appends 'event' broadcasts) shows it —
    # a status-only broadcast is silently invisible there.
    return [Broadcast("event" if ev is not None else "status", track, ev)]


async def _handle_impact(ctx: IngestContext) -> list[Broadcast]:
    """Impact / confirmed strike location ("влучання по будівлі в
    Дніпровському районі", "у Святошинському... пошкоджено будівлю"). This is
    a HIT, not an active inbound target — record it as its own terminal
    marker (closed immediately) so it persists on the map as a distinct
    impact pin and appears in the feed, without being mistaken for a target
    still in the air or absorbing later sightings over that district. Being
    closed, it's invisible to all track continuation/closure logic (which all
    filter closed_at IS NULL). Target type is whatever this message stated or
    inherited (often ballistic mid-attack)."""
    session, parsed, when = ctx.session, ctx.parsed, ctx.when
    # ONE impact marker PER DISTRICT — never merge districts into a single
    # threat. An impact is a POINT strike, not a trajectory: a ballistic can't
    # "move" Дарницький->Святошинський, yet a shared multi-district threat drew
    # exactly that bogus vector once later re-reports gave it several timestamps
    # (live 2026-07-15: T244 zigzagged two districts). Per district: a recent
    # impact over the SAME district is the SAME strike (two sources, one hit) ->
    # corroborate its marker; a different district gets its own marker.
    impacts: list[Broadcast] = []
    tracks_seen: list[Threat] = []
    for hit in parsed.districts:
        track = await find_recent_impact(session, hit.district_id, when)
        if track is None:
            track = Threat(
                target_type=parsed.target_type,
                status="impact",
                kind="impact",
                target_count=parsed.target_count or 1,
                created_at=when,
                closed_at=when,
            )
            session.add(track)
            await session.flush()
            log.info("track %s created (kind=impact, target_type=%s)", track.id, track.target_type)
        else:
            track.target_type = _upgrade_type(track.target_type, parsed.target_type)
        if track not in tracks_seen:
            tracks_seen.append(track)
        ev = _make_event(ctx, track.id, hit, target_count=track.target_count)
        session.add(ev)
        # apply_fusion autoflushes the new track+event and commits them together.
        await apply_fusion(session, track)
        impacts.append(Broadcast("event", track, ev))
    # Every distinct impact marker joins the same attack (one barrage, many
    # hits); broadcast the incident once after the last attach.
    attack_bc = None
    for track in tracks_seen:
        attack_bc = await _incident_broadcast(ctx, track)
    if attack_bc is not None:
        impacts.append(attack_bc)
    await ctx.done()
    return impacts


async def _handle_citywide(ctx: IngestContext) -> list[Broadcast]:
    """City-wide threat ("Ціль на місто!", "Балістика на Київ") — a strike
    aimed at the city as a whole that no spotter has localized to a raion
    (the sub-minute ballistic phase, when the map would otherwise be empty).
    Raise ONE city-level alert: continue an open one (repeated callouts
    corroborate it) or start a fresh one. Its event attaches to the sentinel
    district so it has a valid point; the frontend renders it as a banner,
    not a pin. Type upgrades like a normal track, so a bare "на місто" after
    "Балістика!" inherits ballistic (see type inheritance)."""
    session, parsed, when = ctx.session, ctx.parsed, ctx.when
    did = await citywide_district_id(session)
    if did is None:  # sentinel not seeded (shouldn't happen post-startup) — skip
        await ctx.done()
        return []
    track = await find_open_citywide(session, when)
    if track is None:
        stood = await find_stood_down_citywide(session, when)
        if stood is not None:
            track = reopen_track(stood)
    if track is None:
        track = _new_track(parsed, when, scope="city")
        session.add(track)
        await session.commit()
        log.info("track %s created (scope=city, target_type=%s)", track.id, track.target_type)
    else:
        _apply_update(parsed, track)
    ev = _make_event(ctx, track.id, DistrictHit(did, "", 0), target_count=track.target_count)
    session.add(ev)
    await session.commit()
    await apply_fusion(session, track)
    out = [Broadcast("event", track, ev), await _incident_broadcast(ctx, track)]
    await _append_axis(ctx, out)
    await ctx.done()
    return out


async def _handle_sighting(ctx: IngestContext) -> list[Broadcast]:
    """Sighting / confirmed / unconfirmed -> continue or start a track.
    (1) reply to an OPEN chain = authoritative same-target signal (beats
    is_new_target); (2) else corroboration — continue only a track recently
    over the same district; (3) else a new track. A reply into a CLOSED chain
    falls through to (2)/(3), so it won't glue onto the newest track."""
    session, parsed, when = ctx.session, ctx.parsed, ctx.when
    # Enumeration split is BALLISTIC-only: a ballistic salvo's «Вишневе Жуляни»
    # is two simultaneous impacts-in-seconds (gluing them zigzagged the map on
    # 07-18 and let the glued track steal later single-district callouts). On a
    # drone night the same shape («Троя,Оболонь») is usually ONE drone
    # meandering between adjacent raions — the track-eval ground truth
    # (drone/cruise nights) loses 16 points of session purity if those split,
    # and ballistic tracks never draw vectors anyway, so nothing is lost there.
    if (parsed.multi_targets and parsed.target_type == "ballistic"
            and not ctx.type_from_incident):
        return await _handle_multi_targets(ctx)
    track = await find_track_by_reply(session, ctx.source_id, ctx.reply_to_message_id)
    if track is None and not parsed.is_new_target:
        district_ids = {h.district_id for h in parsed.districts}
        track = await find_corroborating_track(session, when, district_ids, as_of=ctx.as_of)
        if track is None:
            stood = await find_stood_down_track(session, when, district_ids)
            if stood is not None:
                track = reopen_track(stood)
    if track is None:
        track = _new_track(parsed, when)
        session.add(track)
        await session.commit()
        log.info("track %s created (target_type=%s)", track.id, track.target_type)
    else:
        # Group size only grows within a chain (2х -> "їх вже 3х").
        _apply_update(parsed, track)

    broadcasts: list[Broadcast] = []
    # One event per mentioned district, in movement order. Add them all, then
    # fuse ONCE — apply_fusion autoflushes+commits, so this is a single
    # transaction for the whole multi-raion callout instead of one per district
    # (fewer writes under the ingest lock; final track state is identical since
    # fusion recomputes from all events regardless).
    for hit in parsed.districts:
        ev = _make_event(ctx, track.id, hit, target_count=track.target_count)
        session.add(ev)
        broadcasts.append(Broadcast("event", track, ev))
    await apply_fusion(session, track)

    broadcasts.append(await _incident_broadcast(ctx, track))
    await _append_axis(ctx, broadcasts)
    await ctx.done()
    return broadcasts


async def _handle_multi_targets(ctx: IngestContext) -> list[Broadcast]:
    """A bare enumeration of districts ("Вишневе Жуляни", "Особливо Поділ,
    Святошин та Жуляни!") names SIMULTANEOUS separate targets — each district
    continues/starts its OWN track. Gluing them all onto one track (the old
    behavior) recreated the zigzag mega-track on 07-18 AND poisoned
    corroboration: the glued track's "latest district" kept stealing the next
    single-district callouts from their real tracks. Reply-joining is skipped
    on purpose — one reply chain can't own several simultaneous targets."""
    session, parsed, when = ctx.session, ctx.parsed, ctx.when
    broadcasts: list[Broadcast] = []
    attack_bc = None
    for hit in parsed.districts:
        track = None
        if not parsed.is_new_target:
            track = await find_corroborating_track(session, when, {hit.district_id},
                                                   as_of=ctx.as_of)
            if track is None:
                stood = await find_stood_down_track(session, when, {hit.district_id})
                if stood is not None:
                    track = reopen_track(stood)
        if track is None:
            # Each named district is ONE target here — the enumeration itself is
            # the count (N districts = N targets). A stated group size in the
            # SAME message ("35 балістичних ракет … по районах: …") is the whole
            # salvo TOTAL, not a per-district count, so it must NOT be stamped on
            # every district track — that multiplied 35× per raion and the
            # journal, summing target_count across tracks, reported hundreds of
            # phantom targets for one bulletin.
            track = _new_track(parsed, when, target_count=1)
            session.add(track)
            await session.flush()
            log.info("track %s created (target_type=%s, multi-target enumeration)",
                     track.id, track.target_type)
        else:
            _apply_update(parsed, track, grow_count=False)
        ev = _make_event(ctx, track.id, hit, target_count=track.target_count)
        session.add(ev)
        # apply_fusion autoflushes the new track+event and commits them together.
        await apply_fusion(session, track)
        broadcasts.append(Broadcast("event", track, ev))
        attack_bc = await _incident_broadcast(ctx, track)
    if attack_bc is not None:
        broadcasts.append(attack_bc)
    await _append_axis(ctx, broadcasts)
    await ctx.done()
    return broadcasts


def _ingest_outcome(broadcasts: list[Broadcast]) -> str:
    """Domain result of one pipeline pass, for the Logfire span — the thing
    auto-instrumentation can't see. `threat` = a real map target/impact was
    created or corroborated (an event fired); `notice` = only informational
    surfaces (directional/summary/clear/status-only/axis); `dropped` = nothing
    actionable, raw row kept but no broadcast."""
    if any(b.type == "event" for b in broadcasts):
        return "threat"
    if broadcasts:
        return "notice"
    return "dropped"


async def _city_alert_open(session) -> bool:
    """Whether the OFFICIAL city air-raid alert is currently running."""
    return await session.scalar(
        select(Alert.id).where(Alert.scope == "city", Alert.ended_at.is_(None))
    ) is not None


def _only_closes(parsed: ParseResult) -> bool:
    """Whether this message can only ever CLOSE state, never open any.

    A stand-down that also carries a live directional threat («Дорозвідка
    триває, але триває загроза балістики з Брянщини») opens an axis, so it
    doesn't qualify."""
    if parsed.status in ("clear", "destroyed"):
        return True
    return parsed.lost_signal and not parsed.directional


async def _dispatch(ctx: IngestContext) -> list[Broadcast]:
    """Route a parsed spotter message to its handler, in fixed precedence order."""
    parsed = ctx.parsed

    # 0. Age veto. A reconnect backfill replays history, and a message that
    #    reaches us a stale-window after it was posted must not OPEN anything:
    #    live 2026-08-02, a 00:14 sighting was stored at ~00:28 (after its own
    #    reply-child, which had therefore already started its own track), and
    #    created a THIRD track plus a brand-new incident ~10s after the відбій —
    #    a fresh attack card for an attack that was over. Closing messages are
    #    deliberately still honoured: re-ingesting a missed "відбій" from the
    #    gap is the whole point of backfilling after a reconnect.
    if ctx.arrived_late() and not _only_closes(parsed):
        log.info("dropping late message (raw %s): posted %s, nothing it opens can be live",
                 ctx.raw.id, ctx.when)
        await ctx.done()
        return []
    # 2a. All-clear. An authoritative FULL "Відбій тривоги" (clear_scope=None,
    #     closes EVERY track) comes ONLY from the official alert channel
    #     (process_parsed_alert closes all tracks on its city end) — a spotter's
    #     full відбій is informal/premature/noisy (the N85 case, plus the whole
    #     "чекаємо/будемо очікувати відбій" class) and must not close every live
    #     track, so it is inert here. A TYPE-SCOPED spotter stand-down ("Відбій
    #     балістичної загрози" -> ballistic only) is KEPT: a narrow tactical
    #     signal the city/oblast-level official alert structurally can't express.
    if parsed.status == "clear":
        if parsed.clear_scope is None:
            await ctx.done()
            return []
        return await _handle_clear(ctx)

    # 2a-bis. "Дорозвідка" stand-down. A MIXED message («Дорозвідка триває, але
    #     паралельно триває загроза балістики з Брянщини…») carries a live
    #     directional threat next to the stand-down — the live half wins (raise
    #     the axis, don't close everything on it): on 07-18 such a message was
    #     swallowed as a plain stand-down while warning of 3 launch directions.
    if parsed.lost_signal:
        if parsed.directional:
            return await _handle_directional(ctx)
        return await _handle_lost_signal(ctx)

    # 2a-ter. Terse target/launch pulse — falls through to the checks below
    #     when there's no open city-wide alert to corroborate.
    if parsed.target_pulse:
        result = await _handle_target_pulse(ctx)
        if result is not None:
            return result

    # 2a-quater. Retrospective attack summary.
    if parsed.summary:
        return await _handle_summary(ctx)

    # 2a-quinquies. Directional/origin callout with no raion -> a map axis.
    if parsed.directional:
        return await _handle_directional(ctx)

    # 2b. Nothing localizable/actionable — keep the raw row, emit nothing.
    if not parsed.matched:
        await ctx.done()
        return []

    # 2c. Destroyed.
    if parsed.status == "destroyed":
        return await _handle_destroyed(ctx)

    # 2c-bis. Impact / confirmed strike location.
    if parsed.impact:
        return await _handle_impact(ctx)

    # 2c-ter. City-wide threat.
    if parsed.citywide:
        return await _handle_citywide(ctx)

    # 2d. Sighting / confirmed / unconfirmed -> continue or start a track.
    return await _handle_sighting(ctx)


async def _make_notice(session, kind: str, parsed: ParseResult, source_id: int | None,
                        when, message_id: int | None = None) -> Notice:
    notice = Notice(kind=kind, text=parsed.raw_text, target_type=parsed.target_type,
                    source_id=source_id, event_time=when, source_message_id=message_id)
    session.add(notice)
    await session.commit()
    return notice


def _last_district_hit(track: Threat) -> DistrictHit | None:
    """Synthesize a hit for the track's most recently reported district, for a
    closing message that names no district of its own."""
    if not track.events:
        return None
    last = max(track.events, key=lambda e: e.event_time)
    return DistrictHit(district_id=last.district_id, name="", position=0)


def _make_event(ctx: IngestContext, threat_id, hit, *, target_count: int = 1) -> ThreatEvent:
    """A ThreatEvent for `hit` on `threat_id`. Every field except the target and
    its count is read straight off `ctx`, so callers pass only what varies."""
    parsed = ctx.parsed
    return ThreatEvent(
        threat_id=threat_id,
        district_id=hit.district_id,
        raw_text=parsed.raw_text,
        event_time=ctx.when,
        confidence=parsed.confidence,
        decision_source=ctx.decision_source,
        source_id=ctx.source_id,
        source_message_id=ctx.message_id,
        forwarded_from_id=ctx.forwarded_from_id,
        forwarded_from_channel_id=ctx.forwarded_from_channel_id,
        reply_to_message_id=ctx.reply_to_message_id,
        event_target_type=parsed.target_type,
        event_target_count=target_count,
        llm_summary=ctx.llm_summary,
    )

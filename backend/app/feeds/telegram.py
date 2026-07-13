"""Telethon MTProto listener: reads configured channels (public usernames or
private invite links) and feeds every new message into the real ingest pipeline.

Auth: needs api_id/api_hash (my.telegram.org) and a session created once via
`python -m app.telegram_login`. Reads only — never posts. Respect Telegram ToS
and use the data for personal/local notification only (spec §12).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from ..config import settings
from ..db import SessionLocal
from ..models import Source
from ..pipeline.broadcast import broadcast_results
from ..pipeline.ingest import ingest_alert_message, ingest_message
from .common import build_matcher
from .health import _state

log = logging.getLogger("telegram")

# Reconnect backoff schedule for run_listener()'s retry loop.
_RECONNECT_INITIAL_SECONDS = 5
_RECONNECT_MAX_SECONDS = 300


def make_session():
    """A file-backed session locally, or a StringSession (env var, no disk
    needed) when TELEGRAM_SESSION_STRING is set — the latter is how Railway
    runs this, since its filesystem doesn't persist across deploys."""
    if settings.telegram_session_string:
        from telethon.sessions import StringSession

        return StringSession(settings.telegram_session_string)
    return settings.telegram_session


def _invite_hash(raw: str) -> str | None:
    """Extract the invite hash from a private-channel link, else None."""
    for marker in ("t.me/+", "t.me/joinchat/", "telegram.me/+"):
        if marker in raw:
            return raw.split(marker, 1)[1].strip("/ ")
    if raw.startswith("+"):
        return raw[1:]
    return None


async def _resolve_channel(client, raw: str):
    """Resolve a channel entry (username / id / invite link) to a Telethon entity."""
    from telethon import functions

    invite = _invite_hash(raw)
    if invite:
        r = await client(functions.messages.CheckChatInviteRequest(invite))
        chat = getattr(r, "chat", None)
        if chat is not None:  # ChatInviteAlready -> already a member
            return chat
        # Not a member yet: join via the invite, then use the resulting chat.
        upd = await client(functions.messages.ImportChatInviteRequest(invite))
        return upd.chats[0]
    return await client.get_entity(raw)


def _source_key(entity) -> str:
    return getattr(entity, "username", None) or f"tg{entity.id}"


def _fwd_origin(m) -> tuple[int | None, int | None]:
    """(forwarded_from_id, forwarded_from_channel_id) for a repost, else
    (None, None). The channel id is the origin's raw Telegram peer id — used
    by fusion.py to disambiguate two different channels whose reposted
    messages happen to share a numeric message id (see _origin_keys)."""
    f = getattr(m, "fwd_from", None)
    if f is None:
        return None, None
    msg_id = getattr(f, "channel_post", None)
    channel_id = None
    from_id = getattr(f, "from_id", None)
    if from_id is not None:
        from telethon import utils

        channel_id = utils.get_peer_id(from_id)
    return msg_id, channel_id


def _reply_to_id(m) -> int | None:
    """The id of the message `m` replies to (same channel), else None.

    Telethon exposes this via the `reply_to` header (`reply_to_msg_id`); older
    builds kept a flat `reply_to_msg_id` attribute — support both.
    """
    header = getattr(m, "reply_to", None)
    if header is not None:
        return getattr(header, "reply_to_msg_id", None)
    return getattr(m, "reply_to_msg_id", None)


async def _ensure_sources(entities, entity_roles: dict[int, str]) -> tuple[dict[int, int], dict[int, str]]:
    """Ensure a Source row per channel; return (id_to_source, source_role).

    id_to_source maps BOTH the raw entity id and the marked peer id (what
    `event.chat_id` returns) to source_id, so live events and backfill both
    resolve their source. source_role maps source_id -> Source.role, so the
    caller can dispatch each message to the spotter or alert ingest path.
    `entity_roles` (entity.id -> 'spotter'|'alert') is kept in sync onto an
    already-existing Source row too, in case a channel moved between the
    TELEGRAM_CHANNELS/ALERT_CHANNELS config lists.
    """
    from telethon import utils

    async with SessionLocal() as s:
        existing = {x.channel_key: x for x in await s.scalars(select(Source))}
        id_map: dict[int, int] = {}
        role_by_source: dict[int, str] = {}
        for e in entities:
            key = _source_key(e)
            role = entity_roles.get(e.id, "spotter")
            src = existing.get(key)
            if src is None:
                src = Source(channel_key=key, name=getattr(e, "title", key), role=role)
                s.add(src)
                await s.flush()
                existing[key] = src
            elif src.role != role:
                src.role = role
            id_map[e.id] = src.id
            id_map[utils.get_peer_id(e)] = src.id  # marked id (== event.chat_id)
            role_by_source[src.id] = src.role
        await s.commit()
        return id_map, role_by_source


async def _ingest_one(s, *, role: str, text: str, when, source_id, message_id,
                      matcher=None, forwarded_from_id=None, forwarded_from_channel_id=None,
                      reply_to_message_id=None):
    """Dispatch one message to the spotter or alert ingest pipeline by role."""
    if role == "alert":
        return await ingest_alert_message(
            s, text=text, when=when, source_id=source_id, message_id=message_id
        )
    return await ingest_message(
        s, text=text, matcher=matcher, when=when,
        source_id=source_id, message_id=message_id,
        forwarded_from_id=forwarded_from_id,
        forwarded_from_channel_id=forwarded_from_channel_id,
        reply_to_message_id=reply_to_message_id,
    )


async def _backfill(client, entities, id_to_source, source_role, matcher) -> None:
    """Ingest recent history across ALL channels in true chronological order, so
    cross-channel corroboration and track grouping work the same as live."""
    collected = []
    for e in entities:
        src_id = id_to_source.get(e.id)
        for m in await client.get_messages(e, limit=settings.telegram_backfill):
            text = getattr(m, "message", "") or ""
            if text.strip():
                collected.append((m.date, src_id, m, text))
    collected.sort(key=lambda x: x[0])  # global oldest -> newest by real timestamp

    stream = settings.telegram_backfill_broadcast
    for when, src_id, m, text in collected:
        role = source_role.get(src_id, "spotter")
        fwd, fwd_channel = _fwd_origin(m)
        try:
            async with SessionLocal() as s:
                results = await _ingest_one(
                    s, role=role, text=text, when=when, source_id=src_id, message_id=m.id,
                    matcher=matcher, forwarded_from_id=fwd, forwarded_from_channel_id=fwd_channel,
                    reply_to_message_id=_reply_to_id(m),
                )
                if stream and results:
                    await broadcast_results(s, results)
        except asyncio.CancelledError:
            raise
        except Exception:
            # One bad message must not abort the whole backfill — the rest of
            # the batch (and every other channel) should still land.
            log.exception("backfill failed on message_id=%s", m.id)
        if stream:
            await asyncio.sleep(0.1)  # let the UI feed fill visibly
    log.info("backfill ingested %d recent messages", len(collected))


async def _run_listener_once(backfill: bool, run_state: dict) -> None:
    """One connect→backfill→listen cycle. Raises on any failure or disconnect
    so the caller's retry loop can reconnect; never returns normally except
    via clean cancellation. Sets run_state["reached_connected"] = True as soon
    as we're live, even if a later exception propagates — lets the caller
    reset its backoff after a run that was actually connected for a while
    (vs. one that failed before connecting at all)."""
    from telethon import TelegramClient, events

    client = TelegramClient(
        make_session(), settings.telegram_api_id, settings.telegram_api_hash
    )
    try:
        await client.start()

        # One client watches both spotter and official-alert channels; each
        # message is routed by its Source.role (see _ingest_one) rather than
        # needing two separate connections/sessions.
        channel_specs = (
            [(c, "spotter") for c in settings.telegram_channel_list]
            + [(c, "alert") for c in settings.alert_channel_list]
        )
        entities = []
        entity_roles: dict[int, str] = {}
        for raw, role in channel_specs:
            try:
                e = await _resolve_channel(client, raw)
                entities.append(e)
                entity_roles[e.id] = role
            except Exception as ex:
                log.error("could not resolve channel %r: %s", raw, ex)
        if not entities:
            raise RuntimeError("no channels resolved")

        id_to_source, source_role = await _ensure_sources(entities, entity_roles)
        matcher = await build_matcher()

        if backfill and settings.telegram_backfill:
            await _backfill(client, entities, id_to_source, source_role, matcher)

        @client.on(events.NewMessage(chats=entities))
        async def handler(event):  # noqa: ANN001
            # Health = feed LIVENESS, not pipeline success — stamp this before
            # any parsing/DB work so a message that later fails ingest still
            # counts as evidence the connection is alive.
            _state["last_message_at"] = datetime.now(timezone.utc)
            text = event.message.message or ""
            if not text.strip():
                return
            source_id = id_to_source.get(event.chat_id)
            role = source_role.get(source_id, "spotter")
            # If the post is a forward, capture the ORIGINAL post id (+ origin
            # channel id) for repost dedup — see fusion.py::_origin_keys.
            fwd, fwd_channel = _fwd_origin(event.message)
            try:
                async with SessionLocal() as s:
                    results = await _ingest_one(
                        s, role=role, text=text, when=event.message.date,
                        source_id=source_id, message_id=event.message.id,
                        matcher=matcher, forwarded_from_id=fwd,
                        forwarded_from_channel_id=fwd_channel,
                        reply_to_message_id=_reply_to_id(event.message),
                    )
                    await broadcast_results(s, results)
            except asyncio.CancelledError:
                raise
            except Exception:
                # A poison message must not kill Telethon's event dispatcher —
                # that would silently stop the WHOLE feed, not just this message.
                log.exception("live ingest failed on message_id=%s", event.message.id)

        titles = [getattr(e, "title", _source_key(e)) for e in entities]
        log.info("telegram listener connected; monitoring: %s", titles)
        _state["connected"] = True
        _state["last_error"] = None
        run_state["reached_connected"] = True
        await client.run_until_disconnected()
    finally:
        _state["connected"] = False
        await client.disconnect()


async def run_listener() -> None:
    has_channels = settings.telegram_channel_list or settings.alert_channel_list
    if not has_channels or not settings.telegram_api_id:
        log.warning("telegram listener not configured (channels/api_id missing)")
        return

    backoff = _RECONNECT_INITIAL_SECONDS
    first_attempt = True
    while True:
        run_state: dict = {}
        try:
            await _run_listener_once(backfill=first_attempt, run_state=run_state)
            log.warning("telegram listener disconnected cleanly; reconnecting")
        except asyncio.CancelledError:
            raise
        except Exception as ex:
            log.exception("telegram listener crashed: %s", ex)
            _state["last_error"] = str(ex)
        first_attempt = False

        if run_state.get("reached_connected"):
            backoff = _RECONNECT_INITIAL_SECONDS  # was actually live — retry fast
        log.info("reconnecting telegram listener in %ss", backoff)
        await asyncio.sleep(backoff)
        if not run_state.get("reached_connected"):
            backoff = min(backoff * 2, _RECONNECT_MAX_SECONDS)

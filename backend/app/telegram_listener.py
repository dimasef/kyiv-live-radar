"""Telethon MTProto listener: reads configured channels (public usernames or
private invite links) and feeds every new message into the real ingest pipeline.

Auth: needs api_id/api_hash (my.telegram.org) and a session created once via
`python -m app.telegram_login`. Reads only — never posts. Respect Telegram ToS
and use the data for personal/local notification only (spec §12).
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from .broadcast import broadcast_results
from .config import settings
from .db import SessionLocal
from .ingest import ingest_message
from .models import District, Source
from .parser import DistrictMatcher

log = logging.getLogger("telegram")


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


def _reply_to_id(m) -> int | None:
    """The id of the message `m` replies to (same channel), else None.

    Telethon exposes this via the `reply_to` header (`reply_to_msg_id`); older
    builds kept a flat `reply_to_msg_id` attribute — support both.
    """
    header = getattr(m, "reply_to", None)
    if header is not None:
        return getattr(header, "reply_to_msg_id", None)
    return getattr(m, "reply_to_msg_id", None)


async def _ensure_sources(entities) -> dict[int, int]:
    """Ensure a Source row per channel; return a map from BOTH the raw entity id
    and the marked peer id (what `event.chat_id` returns) to source_id, so live
    events and backfill both resolve their source."""
    from telethon import utils

    async with SessionLocal() as s:
        existing = {x.channel_key: x for x in await s.scalars(select(Source))}
        id_map: dict[int, int] = {}
        for e in entities:
            key = _source_key(e)
            src = existing.get(key)
            if src is None:
                src = Source(channel_key=key, name=getattr(e, "title", key))
                s.add(src)
                await s.flush()
                existing[key] = src
            id_map[e.id] = src.id
            id_map[utils.get_peer_id(e)] = src.id  # marked id (== event.chat_id)
        await s.commit()
        return id_map


async def _backfill(client, entities, id_to_source, matcher) -> None:
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
        fwd = getattr(getattr(m, "fwd_from", None), "channel_post", None)
        async with SessionLocal() as s:
            results = await ingest_message(
                s, text=text, matcher=matcher, when=when,
                source_id=src_id, message_id=m.id, forwarded_from_id=fwd,
                reply_to_message_id=_reply_to_id(m),
            )
            if stream and results:
                await broadcast_results(s, results)
        if stream:
            await asyncio.sleep(0.1)  # let the UI feed fill visibly
    log.info("backfill ingested %d recent messages", len(collected))


async def run_listener() -> None:
    from telethon import TelegramClient, events

    raw_channels = settings.telegram_channel_list
    if not raw_channels or not settings.telegram_api_id:
        log.warning("telegram listener not configured (channels/api_id missing)")
        return

    client = TelegramClient(
        settings.telegram_session, settings.telegram_api_id, settings.telegram_api_hash
    )
    await client.start()

    entities = []
    for raw in raw_channels:
        try:
            entities.append(await _resolve_channel(client, raw))
        except Exception as ex:
            log.error("could not resolve channel %r: %s", raw, ex)
    if not entities:
        log.error("no channels resolved — listener idle")
        return

    id_to_source = await _ensure_sources(entities)
    async with SessionLocal() as s:
        districts = list(await s.scalars(select(District)))
    matcher = DistrictMatcher(districts)

    if settings.telegram_backfill:
        await _backfill(client, entities, id_to_source, matcher)

    @client.on(events.NewMessage(chats=entities))
    async def handler(event):  # noqa: ANN001
        text = event.message.message or ""
        if not text.strip():
            return
        source_id = id_to_source.get(event.chat_id)
        # If the post is a forward, capture the ORIGINAL post id for repost dedup.
        fwd = None
        f = getattr(event.message, "fwd_from", None)
        if f is not None:
            fwd = getattr(f, "channel_post", None)
        async with SessionLocal() as s:
            results = await ingest_message(
                s,
                text=text,
                matcher=matcher,
                when=event.message.date,
                source_id=source_id,
                message_id=event.message.id,
                forwarded_from_id=fwd,
                reply_to_message_id=_reply_to_id(event.message),
            )
            await broadcast_results(s, results)

    titles = [getattr(e, "title", _source_key(e)) for e in entities]
    log.info("telegram listener connected; monitoring: %s", titles)
    await client.run_until_disconnected()

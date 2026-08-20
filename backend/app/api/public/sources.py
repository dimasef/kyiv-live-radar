"""The channels this radar reads — public attribution for the map legend."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import settings
from ...db import get_session
from ...models import Source
from ...schemas import SourceLinkOut

router = APIRouter()

# Telegram's own rule for a public username: 5-32 chars, letters/digits/
# underscore, starting with a letter. Anything else in `channel_key` is either a
# numeric channel id (no public page) or an invite link to a PRIVATE channel,
# and republishing one of those would hand out access we were given, not
# earned.
_PUBLIC_USERNAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")


def public_channel_url(channel_key: str) -> str | None:
    """The channel's public t.me page, or None if it has none."""
    return f"https://t.me/{channel_key}" if _PUBLIC_USERNAME.match(channel_key) else None


@router.get("/sources", response_model=list[SourceLinkOut])
async def list_sources(session: AsyncSession = Depends(get_session)):
    """Every channel currently being read, for the legend's «Джерела» block.

    Active only: an archived channel is not something this map is standing on
    any more, and listing it would credit it for data it no longer provides.

    This project's own channel is excluded (`settings.own_channels`) — the block
    exists to point at the volunteer channels the map stands on, and a link back
    to ourselves is a link to the page the reader already has open.

    Spotters first, then the official alert channel — the ordering answers "who
    reports the targets you are looking at" before "where the siren comes from".
    """
    ours = settings.own_channel_list
    stmt = select(Source).where(Source.is_active.is_(True))
    if ours:
        stmt = stmt.where(Source.channel_key.not_in(ours))
    rows = list(await session.scalars(stmt))
    rows.sort(key=lambda s: (s.role != "spotter", s.name))
    return [
        SourceLinkOut(
            id=s.id,
            name=s.name,
            role=s.role,
            region=s.region,
            url=public_channel_url(s.channel_key),
        )
        for s in rows
    ]

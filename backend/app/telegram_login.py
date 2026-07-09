"""One-time interactive Telegram login to create an MTProto session.

Local dev (writes a session file next to TELEGRAM_SESSION, e.g. kyiv_radar.session):

    cd backend
    TELEGRAM_API_ID=... TELEGRAM_API_HASH=... .venv/bin/python -m app.telegram_login

Railway / any host with an ephemeral filesystem (prints a StringSession —
nothing is written to disk; paste the printed value into the TELEGRAM_SESSION_STRING
env var on that service):

    TELEGRAM_API_ID=... TELEGRAM_API_HASH=... .venv/bin/python -m app.telegram_login --string

Each run is an independent Telegram login (its own session, showing up as its
own entry under Settings > Devices) — run it once per place that needs to
connect, don't share one session file/string across machines.
"""

from __future__ import annotations

import asyncio
import sys

from .config import settings


async def main() -> None:
    from telethon import TelegramClient

    if not settings.telegram_api_id or not settings.telegram_api_hash:
        raise SystemExit("Set TELEGRAM_API_ID and TELEGRAM_API_HASH first.")

    as_string = "--string" in sys.argv[1:]
    if as_string:
        from telethon.sessions import StringSession

        session = StringSession()
    else:
        session = settings.telegram_session

    client = TelegramClient(session, settings.telegram_api_id, settings.telegram_api_hash)
    await client.start()  # prompts for phone + login code interactively
    me = await client.get_me()
    print(f"Logged in as {me.username or me.first_name or me.id}")
    if as_string:
        print("\nTELEGRAM_SESSION_STRING=" + client.session.save())
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

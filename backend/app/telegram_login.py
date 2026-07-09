"""One-time interactive Telegram login to create the MTProto session file.

Run it yourself from a terminal (it prompts for your phone number and the code
Telegram sends you):

    cd backend
    TELEGRAM_API_ID=... TELEGRAM_API_HASH=... .venv/bin/python -m app.telegram_login

After it prints "Logged in as ...", the session file (TELEGRAM_SESSION) is saved
and the worker/listener can connect non-interactively.
"""

from __future__ import annotations

import asyncio

from .config import settings


async def main() -> None:
    from telethon import TelegramClient

    if not settings.telegram_api_id or not settings.telegram_api_hash:
        raise SystemExit("Set TELEGRAM_API_ID and TELEGRAM_API_HASH first.")

    client = TelegramClient(
        settings.telegram_session, settings.telegram_api_id, settings.telegram_api_hash
    )
    await client.start()  # prompts for phone + login code interactively
    me = await client.get_me()
    print(f"Logged in as {me.username or me.first_name or me.id}")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

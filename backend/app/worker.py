"""Standalone worker entrypoint for the production two-service model (Railway):
an always-on process that holds the MTProto connection and feeds the shared DB.

    python -m app.worker

NOTE: in the two-service model the api and worker are separate processes, so the
in-process WS broadcaster here reaches no clients — production needs Redis /
Postgres LISTEN-NOTIFY to bridge worker -> api. For local single-process dev,
run the listener inside the api via TELEGRAM_ENABLED=true instead.
"""

from __future__ import annotations

import asyncio
import logging

from .feeds.telegram import run_listener
from .migrate import upgrade_to_head
from .seed import seed_districts, seed_sources

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    await upgrade_to_head()
    await seed_districts()
    await seed_sources()
    await run_listener()


if __name__ == "__main__":
    asyncio.run(main())

"""Analyze each channel's conventions to ground track-grouping design.

For every configured channel: how often messages are REPLIES (thread structure),
forwards, carry 🔴, target keywords, or explicit target counts ("2х", "їх вже 3х").
Also prints sample reply pairs so we can confirm reply-based threading (e.g.
"Місто Кия | Безпека" replying to the prior message about the same target).

Reads only; needs the Telegram session — stop the live listener first.

    cd backend && .venv/bin/python eval/channels.py [--limit 150]
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.telegram_listener import _resolve_channel  # noqa: E402

_COUNT = re.compile(r"\d+\s*х\b|їх вже|іще \d|ще \d")
_TARGET = re.compile(r"шахед|бпла|ракет|баліст|реактивн|мопед|герань|каб", re.IGNORECASE)


def _short(t: str | None) -> str:
    return (t or "").splitlines()[0][:60] if t else "(порожньо)"


async def main() -> None:
    limit = 150
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    from telethon import TelegramClient

    client = TelegramClient(settings.telegram_session, settings.telegram_api_id,
                            settings.telegram_api_hash)
    await client.start()

    for raw in settings.telegram_channel_list:
        try:
            entity = await _resolve_channel(client, raw)
        except Exception as ex:
            print(f"skip {raw}: {ex}", file=sys.stderr)
            continue
        msgs = await client.get_messages(entity, limit=limit)
        by_id = {m.id: m for m in msgs}
        texts = [m for m in msgs if getattr(m, "message", None)]
        n = len(texts) or 1
        replies = [m for m in texts if getattr(m, "reply_to_msg_id", None)]
        forwards = [m for m in texts if getattr(m, "fwd_from", None)]
        red = [m for m in texts if "🔴" in (m.message or "")]
        tgt = [m for m in texts if _TARGET.search(m.message or "")]
        counts = [m for m in texts if _COUNT.search(m.message or "")]

        title = getattr(entity, "title", raw)
        print(f"\n=== {title}  ({raw}) ===")
        print(f"  messages w/ text: {len(texts)}")
        print(f"  replies:   {len(replies):3}  ({100*len(replies)//n}%)   <- thread signal")
        print(f"  forwards:  {len(forwards):3}  ({100*len(forwards)//n}%)")
        print(f"  🔴 status: {len(red):3}  ({100*len(red)//n}%)")
        print(f"  target kw: {len(tgt):3}  ({100*len(tgt)//n}%)")
        print(f"  counts(Nх):{len(counts):3}  ({100*len(counts)//n}%)   <- target-count signal")

        pairs = [m for m in replies if m.reply_to_msg_id in by_id][:4]
        if pairs:
            print("  sample reply chains (reply  <-  parent):")
            for m in pairs:
                parent = by_id[m.reply_to_msg_id]
                print(f"    ↳ {_short(m.message)}")
                print(f"        parent: {_short(parent.message)}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

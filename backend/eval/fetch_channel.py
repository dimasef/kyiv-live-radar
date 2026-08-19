"""Read-only: dump the last N messages of ONE channel to JSONL for analysis.

Sizing up a channel BEFORE trusting it as a source — does our parser understand
how it writes? which toponyms does it use? does it reply-thread? — needs its
real text and nothing else. Deliberately unlike eval/backfill_once.py, which
reads the ENV channel list (sources live in the DB now) and WIPES the tracking
tables: this touches no database at all.

Stop the live listener first — it holds the Telethon session file.

    cd backend && .venv/bin/python eval/fetch_channel.py chyste_nebochernigv --limit 300
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.feeds.telegram import _fwd_origin, _resolve_channel  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("channel", help="username / id / t.me invite link (no @ needed)")
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    from telethon import TelegramClient

    out = args.out or Path(__file__).parent / f"{args.channel.lstrip('@')}_sample.jsonl"

    client = TelegramClient(settings.telegram_session, settings.telegram_api_id,
                            settings.telegram_api_hash)
    await client.start()
    try:
        entity = await _resolve_channel(client, args.channel.lstrip("@"))
        print(f"{getattr(entity, 'title', '?')} (id={entity.id}, "
              f"@{getattr(entity, 'username', None)})")
        rows = []
        async for m in client.iter_messages(entity, limit=args.limit):
            if not (m.message or "").strip():
                continue  # media-only post: nothing for the parser to read
            fwd_id, fwd_channel = _fwd_origin(m)
            rows.append({
                "message_id": m.id,
                "date": m.date.isoformat(),
                "text": m.message,
                "reply_to_message_id": getattr(m.reply_to, "reply_to_msg_id", None),
                "forwarded_from_id": fwd_id,
                "forwarded_from_channel_id": fwd_channel,
            })
    finally:
        await client.disconnect()

    rows.reverse()  # oldest first — chronological, like the live feed
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")
    print(f"wrote {len(rows)} messages to {out}")


if __name__ == "__main__":
    asyncio.run(main())

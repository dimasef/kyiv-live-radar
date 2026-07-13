"""Mine candidate place-names the channels use but the parser misses.

Pulls recent channel history, runs the rule parser, and for messages it could
NOT localize, extracts toponym candidates (words after locational prepositions,
plus "X/Y" slash pairs). Ranks by frequency so we see the real coverage gaps —
the work-list for growing the gazetteer.

Reads only; needs the Telegram session. Stop the live listener first (it holds
the session lock).

    cd backend && .venv/bin/python eval/mine_toponyms.py [--limit 300]
"""

from __future__ import annotations

import asyncio
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.feeds.telegram import _resolve_channel  # noqa: E402
from app.gazetteer import DISTRICTS  # noqa: E402
from app.parsing import DistrictMatcher, normalize, parse_message  # noqa: E402

_PREP = r"(?:на|над|у|в|біля|поблизу|повз|через|під|коло|район[іуа]?|масив[іуа]?|бік)"
_WORD = r"[А-ЯІЇЄҐ][а-яіїєґ'ʼ’\-]{2,}"
_CAND = re.compile(_PREP + r"\s+(" + _WORD + r"(?:\s*/\s*" + _WORD + r")?)", re.IGNORECASE)
_PAIR = re.compile(r"(" + _WORD + r")\s*/\s*(" + _WORD + r")")

# Non-place words that follow the prepositions but aren't toponyms.
_STOP = {"київ", "києві", "київщина", "київщину", "столицю", "столиці", "місто",
         "місті", "цілі", "ціль", "напрямку", "напрямок", "висоті", "заході",
         "сході", "півночі", "півдні", "центр", "центрі", "область", "області",
         "межі", "межу", "підльоті", "групу", "групи", "воду", "зниження"}


def _candidates(text: str) -> list[str]:
    out: list[str] = []
    for m in _CAND.finditer(text):
        chunk = m.group(1)
        pair = _PAIR.search(chunk)
        if pair:
            out += [pair.group(1), pair.group(2)]
        else:
            out.append(chunk.strip())
    for pair in _PAIR.finditer(text):  # bare "X/Y" pairs anywhere
        out += [pair.group(1), pair.group(2)]
    return out


async def main() -> None:
    limit = 300
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    from telethon import TelegramClient

    matcher = DistrictMatcher([{"id": i + 1, **d} for i, d in enumerate(DISTRICTS)])
    client = TelegramClient(settings.telegram_session, settings.telegram_api_id,
                            settings.telegram_api_hash)
    await client.start()

    texts: list[str] = []
    for raw in settings.telegram_channel_list:
        try:
            entity = await _resolve_channel(client, raw)
        except Exception as ex:
            print(f"skip {raw}: {ex}", file=sys.stderr)
            continue
        msgs = await client.get_messages(entity, limit=limit)
        texts += [m.message for m in msgs if getattr(m, "message", None)]
    await client.disconnect()

    counter: Counter[str] = Counter()
    example: dict[str, str] = {}
    missed = 0
    for t in texts:
        if parse_message(t, matcher).districts:
            continue  # already localized by rules
        missed += 1
        for cand in _candidates(t):
            key = normalize(cand)
            if key in _STOP or len(key) < 3:
                continue
            if matcher.find(key):  # already a known district/alias
                continue
            counter[key] += 1
            example.setdefault(key, t.splitlines()[0][:55])

    print(f"\n{len(texts)} messages | {missed} not localized by rules")
    print(f"top unmatched toponym candidates:\n")
    for name, n in counter.most_common(40):
        print(f"  {n:3}  {name:20} | e.g. {example[name]}")


if __name__ == "__main__":
    asyncio.run(main())

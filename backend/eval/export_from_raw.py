"""Build an eval-labeling template from REAL captured messages.

Reads stored `raw_messages`, runs the current parser to PRE-FILL its predictions,
and writes a JSONL template. A human then corrects the labels (that's the ground
truth) and appends the good rows to eval_set.jsonl. This is how the eval set
grows from real channel data instead of hand-invented phrasing (spec §8.11).

    cd backend && .venv/bin/python eval/export_from_raw.py [--limit N] > eval/to_label.jsonl
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.gazetteer import DISTRICTS  # noqa: E402
from app.models import RawMessage  # noqa: E402
from app.parsing import DistrictMatcher, parse_message  # noqa: E402

_ID_TO_EN = {i + 1: d["name_en"] for i, d in enumerate(DISTRICTS)}


def _norm_status(s: str) -> str:
    return "active" if s in ("confirmed", "sighting") else s


async def main() -> None:
    limit = 200
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    matcher = DistrictMatcher([{"id": i + 1, **d} for i, d in enumerate(DISTRICTS)])

    async with SessionLocal() as s:
        rows = list(await s.scalars(
            select(RawMessage).order_by(RawMessage.event_time.desc()).limit(limit)
        ))

    seen: set[str] = set()
    for r in rows:
        text = (r.text or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        res = parse_message(text, matcher)
        # Pre-filled with the parser's guess; the labeler corrects these.
        record = {
            "text": text,
            "target_type": res.target_type,
            "status": _norm_status(res.status),
            "is_new_target": res.is_new_target,
            "districts": sorted(
                filter(None, {_ID_TO_EN.get(h.district_id) for h in res.districts})
            ),
            "_review": "correct the fields above, then move this line to eval_set.jsonl",
        }
        print(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())

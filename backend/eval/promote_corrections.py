"""Emit admin corrections as DRAFT golden-set rows for manual review.

The hand-labeled golden set (eval_set.jsonl) stays curated — we never auto-append
to it. This prints eval_set.jsonl-shaped lines derived from the harvested
corrections so a human can eyeball, complete the fields the operator didn't
assert, and paste the good ones in.

  * false_positive → {"text", "districts": []}                (negative example)
  * retype         → {"text", "target_type", "districts": [<current parser hits>]}
  * relocate       → {"text", "districts": [<corrected district_en>]}

    cd backend && DATABASE_URL=... .venv/bin/python eval/promote_corrections.py > drafts.jsonl
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
from app.models import ParserCorrection  # noqa: E402
from app.parsing import DistrictMatcher, parse_message  # noqa: E402

_ID_TO_EN = {i + 1: d["name_en"] for i, d in enumerate(DISTRICTS)}


def _matcher() -> DistrictMatcher:
    return DistrictMatcher([{"id": i + 1, **d} for i, d in enumerate(DISTRICTS)])


def draft_row(c: ParserCorrection, matcher: DistrictMatcher) -> dict | None:
    exp = c.expected or {}
    if c.kind == "false_positive":
        return {"text": c.text, "districts": []}
    if c.kind == "retype":
        res = parse_message(c.text, matcher)
        districts = sorted(filter(None, (_ID_TO_EN.get(h.district_id) for h in res.districts)))
        return {"text": c.text, "target_type": exp.get("target_type"), "districts": districts}
    if c.kind == "relocate":
        return {"text": c.text, "districts": [exp.get("district_en")]}
    return None


async def _load() -> list[ParserCorrection]:
    async with SessionLocal() as s:
        return list(await s.scalars(select(ParserCorrection).order_by(ParserCorrection.id)))


def main() -> int:
    matcher = _matcher()
    corrections = asyncio.run(_load())
    print("# DRAFT rows — review/complete before adding to eval_set.jsonl", file=sys.stderr)
    for c in corrections:
        row = draft_row(c, matcher)
        if row is not None:
            print(json.dumps(row, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

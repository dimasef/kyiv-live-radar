"""Regression check over admin-harvested parser corrections.

Every /admin override (dismiss / retype / district move) is stored as a
`ParserCorrection` — a labeled statement of what the parser SHOULD have done
(see app/domain/corrections.py). This runs the CURRENT rule parser over each
correction's text and reports how many the parser now agrees with:

  * false_positive → parser must localize NO district (the message was junk)
  * retype         → parser's target_type must match the corrected one
  * relocate       → the corrected district must be among the parser's hits

A rising "fixed" ratio means parser/gazetteer work is retiring real mistakes; a
"still wrong" list is a concrete to-do. Read-only — never mutates the DB.

    cd backend && DATABASE_URL=... .venv/bin/python eval/corrections_eval.py [--verbose]
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.domain.corrections import parser_agrees  # noqa: E402
from app.gazetteer import DISTRICTS  # noqa: E402
from app.models import ParserCorrection  # noqa: E402
from app.parsing import DistrictMatcher  # noqa: E402

# Offline eval uses gazetteer-index ids (matches app/parsing DistrictMatcher
# built the same way); the app endpoint uses real DB ids instead.
_ID_TO_EN = {i + 1: d["name_en"] for i, d in enumerate(DISTRICTS)}


def _matcher() -> DistrictMatcher:
    return DistrictMatcher([{"id": i + 1, **d} for i, d in enumerate(DISTRICTS)])


def check(correction: ParserCorrection, matcher: DistrictMatcher) -> tuple[bool, str]:
    return parser_agrees(correction, matcher, _ID_TO_EN)


async def _load() -> list[ParserCorrection]:
    async with SessionLocal() as s:
        return list(await s.scalars(select(ParserCorrection).order_by(ParserCorrection.id)))


def main() -> int:
    verbose = "--verbose" in sys.argv
    matcher = _matcher()
    corrections = asyncio.run(_load())
    if not corrections:
        print("No corrections recorded yet — nothing to check.")
        return 0

    by_kind: dict[str, list[int]] = {}
    still_wrong: list[str] = []
    for c in corrections:
        agrees, detail = check(c, matcher)
        stats = by_kind.setdefault(c.kind, [0, 0])
        stats[1] += 1
        if agrees:
            stats[0] += 1
        else:
            still_wrong.append(f"  [{c.kind}] {c.text[:70]!r} — {detail}")

    total_fixed = sum(v[0] for v in by_kind.values())
    total = sum(v[1] for v in by_kind.values())
    print(f"\nParser corrections: {total_fixed}/{total} now handled correctly\n")
    for kind, (fixed, n) in sorted(by_kind.items()):
        print(f"  {kind:16} {fixed:3}/{n:<3} ({fixed / n * 100:5.1f}%)")
    if verbose and still_wrong:
        print("\nStill reproduced by the current parser:")
        print("\n".join(still_wrong))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

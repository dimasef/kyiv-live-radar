"""Rules vs. rules+LLM comparison on REAL captured messages (spec §9.5).

For messages the rule parser could NOT localize, calls the Haiku fallback and
reports how many it additionally localizes — the concrete evidence for whether
the LLM earns its cost/latency. Cost-controlled via --limit.

    cd backend && .venv/bin/python eval/compare_llm.py [--limit 15]
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import District, RawMessage  # noqa: E402
from app.parsing import DistrictMatcher, parse_message  # noqa: E402
from app.parsing.llm import llm_extract  # noqa: E402
from app.pipeline.ingest import should_fallback  # noqa: E402


async def main() -> None:
    limit = 15
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    if not settings.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY not set in backend/.env")

    async with SessionLocal() as s:
        districts = list(await s.scalars(select(District)))
        raws = list(await s.scalars(select(RawMessage).order_by(RawMessage.event_time.desc())))
    matcher = DistrictMatcher(districts)

    # Unique texts the rules localized vs. flagged for fallback.
    seen: set[str] = set()
    localized_by_rules = 0
    candidates = []
    for r in raws:
        t = (r.text or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        parsed = parse_message(t, matcher)
        if parsed.districts:
            localized_by_rules += 1
        elif should_fallback(parsed):
            candidates.append(t)

    print(f"\nunique messages: {len(seen)} | localized by rules: {localized_by_rules}")
    print(f"fallback candidates: {len(candidates)} (testing {min(limit, len(candidates))})\n")

    gained = 0
    for t in candidates[:limit]:
        res, _usage, _response = await llm_extract(t, matcher)
        dz = ", ".join(h.name for h in res.districts) if res and res.districts else "—"
        if res and res.districts:
            gained += 1
        flag = "＋" if (res and res.districts) else " "
        print(f"[{flag}] {dz[:26]:26} | {t.splitlines()[0][:52]}")

    tested = min(limit, len(candidates))
    print(f"\nLLM localized {gained}/{tested} of the rule-misses "
          f"({gained/tested*100:.0f}%)" if tested else "\nno candidates")


if __name__ == "__main__":
    asyncio.run(main())

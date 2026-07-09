"""Accuracy analysis over whatever is currently ingested (run after a big
backfill). Prints the ingestion funnel, the tracks with their computed movement
vectors, and a full event dump for eyeballing precision.

    cd backend && .venv/bin/python eval/analyze.py
"""

from __future__ import annotations

import math
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio  # noqa: E402

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import District, RawMessage, Threat, ThreatEvent  # noqa: E402
from app.parser import DistrictMatcher, parse_message  # noqa: E402

_CARDINALS = ["Пн", "ПнСх", "Сх", "ПдСх", "Пд", "ПдЗх", "Зх", "ПнЗх"]


def _bearing(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    dlo = lo2 - lo1
    y = math.sin(dlo) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dlo)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _cardinal(deg: float) -> str:
    return _CARDINALS[round(deg / 45) % 8]


async def main() -> None:
    async with SessionLocal() as s:
        districts = list(await s.scalars(select(District)))
        raws = list(await s.scalars(select(RawMessage)))
        threats = list(await s.scalars(
            select(Threat).order_by(Threat.id).options(
                selectinload(Threat.events).selectinload(ThreatEvent.district),
                selectinload(Threat.events).selectinload(ThreatEvent.source),
            )
        ))
    matcher = DistrictMatcher(districts)

    # --- 1. Ingestion funnel (re-parse rules over unique messages) ---
    seen, localized, aftermath, siren_only, negated, unloc = set(), 0, 0, 0, 0, 0
    for r in raws:
        t = (r.text or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        p = parse_message(t, matcher)
        if p.aftermath:
            aftermath += 1
        elif p.siren_only:
            siren_only += 1
        elif p.negated:
            negated += 1
        elif p.districts:
            localized += 1
        else:
            unloc += 1

    all_events = [e for th in threats for e in th.events]
    src_counter = Counter(e.decision_source for e in all_events)
    tt_counter = Counter(e.event_target_type for e in all_events)
    reply_events = sum(1 for e in all_events if e.reply_to_message_id is not None)

    print("\n=== INGESTION FUNNEL (unique messages, rule pass) ===")
    print(f"  unique messages:        {len(seen)}")
    print(f"  rule-localized:         {localized}")
    print(f"  dropped as aftermath:   {aftermath}")
    print(f"  dropped as siren-only:  {siren_only}")
    print(f"  dropped as negated:     {negated}")
    print(f"  not localized (other):  {unloc}")
    print(f"\n  events written: {len(all_events)}  "
          f"(rule={src_counter.get('rule',0)} llm={src_counter.get('llm',0)})")
    print(f"  event target types: {dict(tt_counter)}")
    print(f"  reply-grouped events:   {reply_events} / {len(all_events)} "
          f"(rest grouped by time-gap fallback)")
    if threats:
        sizes = sorted((len(th.events) for th in threats), reverse=True)
        print(f"  track sizes (desc):     {sizes[:12]}  (max={sizes[0]})")

    # --- 2. Tracks + movement vectors ---
    print(f"\n=== TRACKS ({len(threats)}) — path + vector ===")
    for th in threats:
        pts, path = [], []
        for e in th.events:
            if e.district is None:
                continue
            name = e.district.name_uk
            if not path or path[-1] != name:
                path.append(name)
                pts.append((e.district.lat, e.district.lon))
        vec = "—"
        if len(pts) >= 2:
            b = _bearing(pts[-2], pts[-1])
            vec = f"курс {_cardinal(b)} ({b:.0f}°)"
        state = "open" if th.closed_at is None else th.status
        srcs = len({e.source_id for e in th.events if e.source_id})
        flag = " ⚠conflict" if th.has_conflict else ""
        print(f"  #{th.id:<3} {th.target_type:9} [{state:9}] corrob={th.corroboration_count} "
              f"src={srcs} conf={th.confidence:.2f}{flag}")
        print(f"        шлях: {' → '.join(path) if path else '(немає)'}  | {vec}")

    # --- 3. Full event dump for precision eyeballing ---
    print(f"\n=== EVENTS ({len(all_events)}) — eyeball for false positives ===")
    for e in sorted(all_events, key=lambda e: e.event_time):
        d = e.district.name_uk if e.district else "—"
        src = e.source.name if e.source else "NULL"
        tag = "LLM" if e.decision_source == "llm" else "   "
        print(f"  [{tag}] {d:16} {src:22} | {(e.raw_text or '').splitlines()[0][:52]}")


if __name__ == "__main__":
    asyncio.run(main())

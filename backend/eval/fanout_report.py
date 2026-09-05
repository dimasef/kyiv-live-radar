"""Echo fan-out and path tortuosity on a real database — the gate for the path
rule (plan .claude/plans/target-fanout.md §4.2) and the baseline for the
association gate (§4.3).

Tortuosity compares two polylines per multi-source track: every located
sighting, and only the path source's (domain/path.py). Path length can only
shrink for a sub-polyline; turn count can in principle grow, so both are
printed per group together with how many tracks got worse.

    cd backend
    DATABASE_URL="sqlite+aiosqlite:///./copy.db" .venv/bin/python eval/fanout_report.py [--region kyiv] [--since 2026-08-28] [--verbose]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.domain.geometry import angdiff_deg, bearing_deg, haversine_km  # noqa: E402
from app.domain.path import narrator_source_id, path_source_id  # noqa: E402
from app.models import Source, Threat, ThreatEvent  # noqa: E402
from app.timeutil import naive  # noqa: E402

TURN_DEG = 120.0


def _points(events):
    pts = []
    for e in sorted(events, key=lambda e: naive(e.event_time)):
        d = e.district
        if d is None:
            continue
        if pts and pts[-1] == (d.lat, d.lon):
            continue
        pts.append((d.lat, d.lon))
    return pts


def _length_km(pts):
    return sum(haversine_km(*a, *b) for a, b in zip(pts, pts[1:], strict=False))


def _turns(pts):
    n = 0
    for a, b, c in zip(pts, pts[1:], pts[2:], strict=False):
        h1 = bearing_deg(*a, *b)
        h2 = bearing_deg(*b, *c)
        if abs(angdiff_deg(h1, h2)) > TURN_DEG:
            n += 1
    return n


def _tortuosity(threats, verbose: bool):
    groups = {"narrated": [], "unnarrated": []}
    for t in threats:
        located = [e for e in t.events if e.district is not None]
        if len({e.source_id for e in located if e.source_id is not None}) < 2:
            continue
        psid = path_source_id(located, None)
        all_pts = _points(located)
        path_pts = _points([e for e in located if e.source_id == psid or e.attached_by == "manual"])
        key = "narrated" if narrator_source_id(located) is not None else "unnarrated"
        groups[key].append((t.id, _length_km(all_pts), _length_km(path_pts),
                            _turns(all_pts), _turns(path_pts), psid, t.path_source_id))
    print("\n== Tortuosity: all sightings -> path source (multi-source tracks) ==")
    print(f"{'group':<12}{'tracks':>7}{'len all':>10}{'len path':>10}{'Δ':>7}"
          f"{'turns all':>11}{'turns path':>12}{'Δ':>7}{'worse':>7}")
    for key, rows in groups.items():
        if not rows:
            continue
        la = sum(r[1] for r in rows)
        lp = sum(r[2] for r in rows)
        ta = sum(r[3] for r in rows)
        tp = sum(r[4] for r in rows)
        worse = sum(1 for r in rows if r[4] > r[3] or r[2] > r[1] + 1e-6)
        dl = f"{(lp - la) / la * 100:+.0f}%" if la else "n/a"
        dt = f"{(tp - ta) / ta * 100:+.0f}%" if ta else "n/a"
        print(f"{key:<12}{len(rows):>7}{la:>10.0f}{lp:>10.0f}{dl:>7}{ta:>11}{tp:>12}{dt:>7}{worse:>7}")
        stored_diff = sum(1 for r in rows if r[6] is not None and r[6] != r[5])
        if stored_diff:
            print(f"  {stored_diff} tracks: latched path_source_id differs from a from-scratch pick"
                  " (expected: the live rule switches only on a lead of 2)")
        if verbose:
            for r in sorted(rows, key=lambda r: r[3] - r[4], reverse=True)[:10]:
                print(f"  track {r[0]}: len {r[1]:.1f}->{r[2]:.1f} km, turns {r[3]}->{r[4]}, src {r[5]}")


def _fanout(threats, sources, since, until):
    print("\n== Fan-out ==")
    stale = sum(1 for t in threats if t.closed_reason == "stale")
    if not stale:
        print("no closed_reason='stale' tracks: the rebuild was not swept, peak counts skipped")
    per_day = Counter(naive(t.created_at).date() for t in threats)
    print(f"tracks/day: {sum(per_day.values()) / max(len(per_day), 1):.1f} over {len(per_day)} days")
    by_src: dict[int, list[int]] = defaultdict(list)
    for t in threats:
        for sid, n in Counter(e.source_id for e in t.events).items():
            if sid is not None:
                by_src[sid].append(n)
    print(f"{'source':<28}{'tracks':>7}{'ev/track':>9}{'1-event':>8}{'path lead':>10}")
    lead = Counter(t.path_source_id for t in threats)
    for sid, ns in sorted(by_src.items(), key=lambda kv: -len(kv[1])):
        name = sources.get(sid, str(sid))[:26]
        one = sum(1 for n in ns if n == 1) / len(ns) * 100
        print(f"{name:<28}{len(ns):>7}{sum(ns) / len(ns):>9.1f}{one:>7.0f}%{lead[sid]:>10}")
    if stale:
        events = sorted(
            [(naive(t.created_at), 1) for t in threats]
            + [(naive(t.closed_at), -1) for t in threats if t.closed_at is not None]
        )
        peak = cur = 0
        for _, d in events:
            cur += d
            peak = max(peak, cur)
        print(f"peak simultaneous open tracks: {peak}")


async def main(region: str, since: datetime | None, until: datetime | None, verbose: bool):
    async with SessionLocal() as s:
        sources = {src.id: src.name for src in await s.scalars(select(Source))}
        stmt = (
            select(Threat)
            .where(Threat.region == region, Threat.kind == "track", Threat.scope == "district")
            .options(selectinload(Threat.events).selectinload(ThreatEvent.district))
        )
        if since is not None:
            stmt = stmt.where(Threat.created_at >= since)
        if until is not None:
            stmt = stmt.where(Threat.created_at < until)
        threats = [t for t in await s.scalars(stmt) if t.status != "dismissed"]
    print(f"{len(threats)} tracks, region={region}, since={since}, until={until}")
    _tortuosity(threats, verbose)
    _fanout(threats, sources, since, until)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="kyiv")
    ap.add_argument("--since", type=datetime.fromisoformat)
    ap.add_argument("--until", type=datetime.fromisoformat)
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.region, a.since, a.until, a.verbose))

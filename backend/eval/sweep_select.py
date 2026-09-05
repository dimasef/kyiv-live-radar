"""Pick the association-gate configuration from a finished rebuild grid
(eval/sweep_rebuilds.sh output), by the rule fixed in the plan BEFORE the grid
ran (.claude/plans/target-fanout.md §4.1):

  among configurations whose contamination counters stay within the gates
  recorded in the ground truth (`_meta.gates`), take the lowest peak of
  simultaneous open tracks; tie-break on the smaller ambiguity margin.

Prints every configuration as one row, then the pick — or "none passed", in
which case release B ships with radius 0 and the per-source stale rule only if
that passes on its own.

    cd backend && python3 eval/sweep_select.py eval/sweep_out
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

GT = Path(__file__).parent / "ground_truth_kyiv_2026-09.json"


def _env(dir_: Path) -> dict[str, str]:
    txt = (dir_ / "config.txt").read_text().strip() if (dir_ / "config.txt").exists() else ""
    return dict(kv.split("=", 1) for kv in txt.split() if "=" in kv)


def _grep(path: Path, pattern: str, group: int = 1, cast=float):
    if not path.exists():
        return None
    m = re.search(pattern, path.read_text())
    return cast(m.group(group)) if m else None


def load(out: Path) -> list[dict]:
    rows = []
    for d in sorted(p for p in out.iterdir() if p.is_dir()):
        gt = d / "gt.json"
        if not gt.exists():
            continue
        r = json.loads(gt.read_text())
        env = _env(d)
        nearby_txt = _grep(d / "rebuild.log", r"nearby: (\{.*\})", cast=str)
        rows.append({
            "name": d.name,
            "city": float(env.get("ASSOCIATION_RADIUS_KM_CITY", 0)),
            "oblast": float(env.get("ASSOCIATION_RADIUS_KM_OBLAST", 0)),
            "margin": float(env.get("AMBIGUITY_MARGIN", 0.3)),
            "stale": env.get("STALE_RULE", "legacy"),
            **{k: r["total"][k] for k in ("foreign_events", "contaminated_tracks",
                                           "split_sessions", "extra_tracks", "labeled_tracks")},
            "tiers": r["tiers"],
            "peak": _grep(d / "fanout.txt", r"peak simultaneous open tracks: (\d+)", cast=int),
            "tracks_day": _grep(d / "fanout.txt", r"tracks/day: ([\d.]+)"),
            "nearby": ast.literal_eval(nearby_txt) if nearby_txt else {},
            "legacy_session_purity": _grep(d / "legacy.txt", r"pure \(correctly one track\):\s+\d+ / \d+ \((\d+)%\)"),
            "legacy_merged": _grep(d / "legacy.txt", r"merged \(2\+ real targets in one\):\s+(\d+) /", cast=int),
        })
    return rows


def main(out: Path) -> int:
    gates = json.loads(GT.read_text())["_meta"].get("gates", {})
    rows = load(out)
    if not rows:
        print("no finished configurations in", out)
        return 1
    hdr = ("name", "city", "obl", "mrg", "stale", "foreign", "contam", "split", "+trk", "peak",
           "trk/d", "prox%", "ambig", "raion", "lg_merged")
    print("".join(f"{h:>10}" for h in hdr))
    for r in rows:
        tiers = r["tiers"]
        n = sum(tiers.values()) or 1
        r["ok"] = all(r[k] <= v for k, v in gates.items())
        print("".join(f"{v:>10}" for v in (
            r["name"][:9], r["city"], r["oblast"], r["margin"], r["stale"][:6],
            r["foreign_events"], r["contaminated_tracks"], r["split_sessions"], r["extra_tracks"],
            r["peak"], r["tracks_day"], round(100 * tiers.get("proximity", 0) / n),
            r["nearby"].get("ambiguous", 0), r["nearby"].get("raion_decided", 0),
            r["legacy_merged"] if r["legacy_merged"] is not None else "-",
        )) + ("" if r["ok"] else "   x gate"))
    passed = [r for r in rows if r["ok"] and r["peak"] is not None]
    print(f"\ngates: {gates}")
    if not passed:
        print("none passed -> release B with radius 0; per_source only if baseline_ps passes")
        return 1
    best = min(passed, key=lambda r: (r["peak"], r["margin"], r["extra_tracks"]))
    print(f"pick: {best['name']}  city={best['city']} oblast={best['oblast']} "
          f"margin={best['margin']} stale={best['stale']}  peak={best['peak']} "
          f"foreign={best['foreign_events']} contaminated={best['contaminated_tracks']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "eval/sweep_out")))

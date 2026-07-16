"""LLM triage quality eval against a hand-labeled set (eval/triage_set.jsonl).

Two modes:
  * (default, CI-able, free) — the DETERMINISTIC half: for every 'directional'
    row, assert the RULES directional predicate (parse_message) fires with the
    right origin. This is the part that must never regress and costs nothing.
  * --live [--limit N] — call the real LLM triage on each row and score
    category accuracy, origin PRECISION (a wrong origin points a wedge the wrong
    way — the dangerous error), and surface precision/recall. Costs API budget;
    run before shipping a prompt/schema change.

Usage:
    .venv/bin/python eval/triage_set.py            # deterministic rules check
    .venv/bin/python eval/triage_eval.py --live --limit 14
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.gazetteer import DISTRICTS  # noqa: E402
from app.parsing import DistrictMatcher, parse_message  # noqa: E402

_SET = Path(__file__).resolve().parent / "triage_set.jsonl"


def _load() -> list[dict]:
    return [json.loads(line) for line in _SET.read_text(encoding="utf-8").splitlines() if line.strip()]


def _matcher() -> DistrictMatcher:
    return DistrictMatcher([{"id": i + 1, **d} for i, d in enumerate(DISTRICTS)])


def run_rules_check(rows: list[dict], matcher: DistrictMatcher) -> int:
    """Deterministic: directional rows must be caught by the rules directional
    predicate with the correct origin. Returns process exit code."""
    dir_rows = [r for r in rows if r["category"] == "directional"]
    ok = 0
    fails: list[str] = []
    for r in dir_rows:
        p = parse_message(r["text"], matcher)
        if p.directional and p.origin_key == r["origin"]:
            ok += 1
        else:
            fails.append(f"  {r['text']!r}: got directional={p.directional} origin={p.origin_key} "
                         f"(want {r['origin']})")
    print(f"=== Triage rules check — {ok}/{len(dir_rows)} directional rows caught ===")
    for f in fails:
        print(f)
    # Also assert non-directional rows are NOT falsely flagged directional.
    false_dir = [r["text"] for r in rows
                 if r["category"] != "directional" and parse_message(r["text"], matcher).directional]
    if false_dir:
        print("  FALSE directional on non-directional rows:")
        for t in false_dir:
            print(f"    {t!r}")
    passed = ok == len(dir_rows) and not false_dir
    print("RESULT:", "PASS" if passed else "FAIL")
    return 0 if passed else 1


async def run_live(rows: list[dict], matcher: DistrictMatcher, limit: int | None) -> int:
    from app.parsing.llm import llm_triage

    rows = rows[:limit] if limit else rows
    cat_ok = origin_tp = origin_fp = 0
    surf_tp = surf_fp = surf_fn = 0
    for r in rows:
        verdict, _ = await llm_triage(r["text"], matcher)
        if verdict is None:
            print(f"  (no verdict) {r['text']!r}")
            continue
        if verdict["category"] == r["category"]:
            cat_ok += 1
        # origin precision: when the model names an origin, is it right?
        got_o, want_o = verdict["origin_place"], r["origin"]
        if got_o != "none":
            if got_o == want_o:
                origin_tp += 1
            else:
                origin_fp += 1
                print(f"  ORIGIN MISS {r['text']!r}: got {got_o} want {want_o}")
        if verdict["surface"] and r["surface"]:
            surf_tp += 1
        elif verdict["surface"] and not r["surface"]:
            surf_fp += 1
        elif not verdict["surface"] and r["surface"]:
            surf_fn += 1
    n = len(rows)
    print(f"=== Triage LIVE eval — {n} rows ===")
    print(f"  category accuracy : {cat_ok}/{n} ({100*cat_ok//max(1,n)}%)")
    o_prec = origin_tp / (origin_tp + origin_fp) if (origin_tp + origin_fp) else 1.0
    print(f"  origin precision  : {o_prec:.2f}  (tp={origin_tp} fp={origin_fp})")
    s_prec = surf_tp / (surf_tp + surf_fp) if (surf_tp + surf_fp) else 1.0
    s_rec = surf_tp / (surf_tp + surf_fn) if (surf_tp + surf_fn) else 1.0
    print(f"  surface P/R       : {s_prec:.2f} / {s_rec:.2f}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="call the real LLM (costs budget)")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    rows = _load()
    matcher = _matcher()
    if args.live:
        return asyncio.run(run_live(rows, matcher, args.limit))
    return run_rules_check(rows, matcher)


if __name__ == "__main__":
    raise SystemExit(main())

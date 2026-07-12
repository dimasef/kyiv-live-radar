"""Parser eval harness.

Runs the rule-based parser over a hand-labeled golden set and reports accuracy:
target-type / status / new-target field accuracy, and district precision/recall
(the safety-critical metric — a missed district means a missed sighting).

Ground-truth labels are what a human considers correct, NOT what the parser
currently outputs — so the report surfaces real gaps to fix or accept.

    cd backend && .venv/bin/python eval/run_eval.py [--verbose]

Exits non-zero if any metric is below its threshold (usable as a CI gate).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.gazetteer import DISTRICTS  # noqa: E402
from app.parser import DistrictMatcher, parse_message  # noqa: E402

EVAL_FILE = Path(__file__).parent / "eval_set.jsonl"

# Minimum acceptable scores. District recall is the strictest — missing a
# sighting is the dangerous failure for this product.
THRESHOLDS = {
    "target_type": 0.85,
    "status": 0.90,
    "is_new_target": 0.90,
    "district_recall": 0.85,
    "district_precision": 0.90,
}

_ID_TO_EN = {i + 1: d["name_en"] for i, d in enumerate(DISTRICTS)}


def _matcher() -> DistrictMatcher:
    return DistrictMatcher([{"id": i + 1, **d} for i, d in enumerate(DISTRICTS)])


def _norm_status(parser_status: str) -> str:
    # Confirmed vs plain sighting is a confidence nuance, not a hard label.
    return "active" if parser_status in ("confirmed", "sighting") else parser_status


def main() -> int:
    verbose = "--verbose" in sys.argv
    matcher = _matcher()
    examples = [json.loads(line) for line in EVAL_FILE.read_text("utf-8").splitlines() if line.strip()]

    n = len(examples)
    ok = {"target_type": 0, "status": 0, "is_new_target": 0}
    tp = fp = fn = 0
    mismatches: list[str] = []
    # Optional boolean flags (decoy/hypersonic — Phase 3; negated — Phase 4):
    # only rows that carry the key are scored, so old rows are untouched.
    # Reported for visibility, not gated by THRESHOLDS — too few examples yet
    # for a hard pass/fail bar.
    OPTIONAL_FLAGS = ("decoy", "hypersonic", "negated")
    opt_ok = {k: 0 for k in OPTIONAL_FLAGS}
    opt_n = {k: 0 for k in OPTIONAL_FLAGS}

    for ex in examples:
        res = parse_message(ex["text"], matcher)
        pred_status = _norm_status(res.status)
        pred_districts = {_ID_TO_EN.get(h.district_id) for h in res.districts}
        exp_districts = set(ex["districts"])

        fields = {
            "target_type": (res.target_type, ex["target_type"]),
            "status": (pred_status, ex["status"]),
            "is_new_target": (res.is_new_target, ex["is_new_target"]),
        }
        row_bad = []
        for key, (pred, exp) in fields.items():
            if pred == exp:
                ok[key] += 1
            else:
                row_bad.append(f"{key}: got {pred!r} exp {exp!r}")

        tp += len(pred_districts & exp_districts)
        fp += len(pred_districts - exp_districts)
        fn += len(exp_districts - pred_districts)
        if pred_districts != exp_districts:
            row_bad.append(f"districts: got {sorted(filter(None, pred_districts))} exp {sorted(exp_districts)}")

        for flag in OPTIONAL_FLAGS:
            if flag not in ex:
                continue
            opt_n[flag] += 1
            pred_flag = getattr(res, flag)
            if pred_flag == ex[flag]:
                opt_ok[flag] += 1
            else:
                row_bad.append(f"{flag}: got {pred_flag!r} exp {ex[flag]!r}")

        if row_bad:
            mismatches.append(f"  · {ex['text']!r}\n      " + "\n      ".join(row_bad))

    recall = tp / (tp + fn) if (tp + fn) else 1.0
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    scores = {
        "target_type": ok["target_type"] / n,
        "status": ok["status"] / n,
        "is_new_target": ok["is_new_target"] / n,
        "district_recall": recall,
        "district_precision": precision,
    }

    print(f"\n=== Parser eval — {n} examples ===\n")
    failed = False
    for key, val in scores.items():
        thr = THRESHOLDS[key]
        mark = "PASS" if val >= thr else "FAIL"
        if val < thr:
            failed = True
        print(f"  {key:20} {val*100:5.1f}%   (min {thr*100:.0f}%)  [{mark}]")
    print(f"  {'district_f1':20} {f1*100:5.1f}%")
    print(f"\n  districts: TP={tp} FP={fp} FN={fn}")
    for flag in OPTIONAL_FLAGS:
        if opt_n[flag]:
            pct = opt_ok[flag] / opt_n[flag] * 100
            print(f"  {flag + ' (informational)':28} {pct:5.1f}%  ({opt_ok[flag]}/{opt_n[flag]})")

    if mismatches and (verbose or failed):
        print(f"\n--- mismatches ({len(mismatches)}) ---")
        print("\n".join(mismatches))

    print()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

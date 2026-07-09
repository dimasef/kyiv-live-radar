"""Runs the parser eval harness as part of the test suite (accuracy gate)."""

import importlib.util
from pathlib import Path

_RUN_EVAL = Path(__file__).resolve().parents[1] / "eval" / "run_eval.py"


def _load_eval():
    spec = importlib.util.spec_from_file_location("run_eval", _RUN_EVAL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_parser_meets_eval_thresholds():
    mod = _load_eval()
    # main() returns 0 when every metric is at/above its threshold.
    assert mod.main() == 0

"""Track-level accuracy gate (eval/track_eval.py) — the thing CLAUDE.md calls
"the thing that actually matters for the map": did each real target end up as
ONE track, or split / merged into a mega-track?

Runs ONLY when eval_backfill.db is present, and is skipped otherwise. That is
not laziness — the dataset genuinely cannot be rebuilt in CI: per the `_meta`
block in eval/ground_truth_sessions.json, the DB comes from a live Telegram
backfill of a moving 300-message window, which needs real credentials. So the
gate runs where the data lives (the maintainer's machine, on every `pytest`),
and CI keeps the per-message gate in test_eval.py, which IS self-contained.

If you have the DB, this fails the suite on a tracking regression instead of
leaving it to someone eyeballing percentages.
"""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_BACKEND = Path(__file__).resolve().parents[1]
_TRACK_EVAL = _BACKEND / "eval" / "track_eval.py"
_DB = _BACKEND / "eval_backfill.db"


def _load_track_eval():
    spec = importlib.util.spec_from_file_location("track_eval", _TRACK_EVAL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.skipif(
    not _DB.exists(),
    reason=(
        "eval_backfill.db absent — rebuild it with the command in "
        "eval/ground_truth_sessions.json::_meta (needs Telegram credentials)"
    ),
)
def test_tracking_meets_track_level_floors(monkeypatch):
    mod = _load_track_eval()
    # The CLI passes DATABASE_URL, but by the time pytest imports anything the
    # app's engine is already bound to the test DB — setting the env var here
    # would be silently ignored and the eval would score the WRONG database
    # (which is exactly what it did before this line existed). Bind the
    # sessionmaker track_eval actually calls.
    engine = create_async_engine(f"sqlite+aiosqlite:///{_DB}")
    monkeypatch.setattr(mod, "SessionLocal", async_sessionmaker(engine, expire_on_commit=False))
    try:
        # main() returns 0 only when every floor in track_eval.MIN_* is met.
        assert mod.main() == 0
    finally:
        import asyncio

        asyncio.run(engine.dispose())


def test_score_gt_counts_foreign_events_and_splits():
    score_gt = _load_track_eval().score_gt
    gt = {
        "sessions": [
            {"session_id": "w1_a", "window": "w1", "message_keys": [["S", 1], ["S", 2]]},
            {"session_id": "w1_b", "window": "w1", "message_keys": [["S", 3]]},
        ],
        "mixed": [{"message_key": ["S", 4]}],
        "not_a_target": [{"message_key": ["S", 5]}],
    }
    rows = [
        (10, ("S", 1), "new", "shahed"),
        (10, ("S", 2), "reply", "shahed"),
        (10, ("S", 3), "district", "shahed"),   # w1_b landed on a's track
        (10, ("S", 5), "inherited", "shahed"),  # stand-down bookkeeping
        (11, ("S", 4), "new", "shahed"),        # mixed only: unlabeled track
        (12, ("S", 9), "new", "shahed"),        # outside the windows
    ]
    r = score_gt(gt, rows)
    t = r["total"]
    assert t["labeled_tracks"] == 1
    assert t["contaminated_tracks"] == 1
    assert t["foreign_events"] == 1
    assert t["not_a_target_events"] == 1
    assert t["split_sessions"] == 0
    assert r["tiers"] == {"new": 1, "reply": 1, "district": 1, "inherited": 1}
    assert r["contaminated_detail"] == {10: ["w1_a", "w1_b"]}

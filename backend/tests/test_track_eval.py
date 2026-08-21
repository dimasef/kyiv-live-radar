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

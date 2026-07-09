"""Track-level accuracy eval: compares hand-labeled REAL target sessions
(eval/ground_truth_sessions.json, built by close-reading 871 real backfilled
messages) against what the tracking pipeline actually produced for those same
messages in eval_backfill.db.

Unlike eval/run_eval.py (per-message field accuracy), this measures the thing
that actually matters for the map/vectors: did each real target end up as ONE
coherent track, or did the pipeline split it into several / merge it with an
unrelated target (the "mega-track" failure mode)?

Build the dataset first (see ground_truth_sessions.json _meta for the exact
command), then:

    cd backend
    DATABASE_URL="sqlite+aiosqlite:///./eval_backfill.db" .venv/bin/python eval/track_eval.py [--verbose]
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Source, ThreatEvent  # noqa: E402

GT_FILE = Path(__file__).parent / "ground_truth_sessions.json"


async def _load_maps():
    """(source_name, telegram_message_id) -> {threat_id, ...}.

    Keyed by the STABLE Telegram identity (channel display name + its
    message_id), not the local raw_messages.id autoincrement — that PK gets
    reassigned every time eval_backfill.db is rebuilt from a fresh Telegram
    fetch, which would silently desync a raw_id-keyed ground truth file.
    """
    async with SessionLocal() as s:
        sources = list(await s.scalars(select(Source)))
        events = list(await s.scalars(select(ThreatEvent)))

    name_by_source_id = {src.id: src.name for src in sources}

    key_to_threat_ids: dict[tuple[str, int], set[int]] = defaultdict(set)
    for e in events:
        name = name_by_source_id.get(e.source_id)
        if name is not None and e.source_message_id is not None:
            key_to_threat_ids[(name, e.source_message_id)].add(e.threat_id)
    return key_to_threat_ids


def main() -> int:
    verbose = "--verbose" in sys.argv
    gt = json.loads(GT_FILE.read_text("utf-8"))
    sessions = gt["sessions"]

    key_to_threat_ids = asyncio.run(_load_maps())

    # --- Per-session: how many distinct pipeline tracks did it get split across? ---
    session_track_sets: dict[str, set[int]] = {}
    session_unmatched: dict[str, list] = {}
    for sess in sessions:
        tids: set[int] = set()
        unmatched = []
        for key in sess["message_keys"]:
            found = key_to_threat_ids.get(tuple(key))
            if found:
                tids |= found
            else:
                unmatched.append(key)
        session_track_sets[sess["session_id"]] = tids
        session_unmatched[sess["session_id"]] = unmatched

    scored = [s for s in sessions if session_track_sets[s["session_id"]]]
    n_scored = len(scored)
    n_pure = sum(1 for s in scored if len(session_track_sets[s["session_id"]]) == 1)
    n_split = n_scored - n_pure

    total_keys = sum(len({tuple(k) for k in s["message_keys"]}) for s in sessions)
    total_unmatched = sum(len(v) for v in session_unmatched.values())

    # --- Per pipeline track: how many distinct GT sessions contributed to it? ---
    track_to_sessions: dict[int, set[str]] = defaultdict(set)
    for sess in sessions:
        for tid in session_track_sets[sess["session_id"]]:
            track_to_sessions[tid].add(sess["session_id"])
    n_tracks = len(track_to_sessions)
    n_tracks_pure = sum(1 for v in track_to_sessions.values() if len(v) == 1)
    n_tracks_merged = n_tracks - n_tracks_pure

    # --- Vector accuracy: GT sessions with real movement (2+ distinct named
    # places) vs whether the mapped pipeline track(s) also span 2+ districts
    # (i.e. would actually draw a vector on the map, per frontend/src/geo.ts). ---
    async def _district_counts():
        async with SessionLocal() as s:
            events = list(await s.scalars(select(ThreatEvent)))
        by_threat: dict[int, set[int]] = defaultdict(set)
        for e in events:
            by_threat[e.threat_id].add(e.district_id)
        return by_threat

    threat_district_counts = asyncio.run(_district_counts())

    movement_sessions = [s for s in scored if len(set(s["district_sequence"])) >= 2]
    vector_would_draw = 0
    for s in movement_sessions:
        tids = session_track_sets[s["session_id"]]
        if any(len(threat_district_counts.get(t, set())) >= 2 for t in tids):
            vector_would_draw += 1

    # --- Report ---
    print(f"\n=== TRACK-LEVEL EVAL — {len(sessions)} ground-truth sessions "
          f"({total_keys} labeled messages) ===\n")
    print(f"  scored (>=1 message localized by rules): {n_scored} / {len(sessions)}")
    print(f"  messages with no rule-parser event (recall gap, LLM was off): "
          f"{total_unmatched} / {total_keys}")
    print()
    print(f"  SESSION PURITY (1 real target -> 1 pipeline track):")
    print(f"    pure (correctly one track):   {n_pure} / {n_scored} "
          f"({100*n_pure/n_scored:.0f}%)" if n_scored else "    n/a")
    print(f"    split across multiple tracks: {n_split} / {n_scored} "
          f"({100*n_split/n_scored:.0f}%)" if n_scored else "    n/a")
    print()
    print(f"  TRACK PURITY (1 pipeline track -> 1 real target, the mega-track check):")
    print(f"    pure (only one real target):     {n_tracks_pure} / {n_tracks} "
          f"({100*n_tracks_pure/n_tracks:.0f}%)" if n_tracks else "    n/a")
    print(f"    merged (2+ real targets in one):  {n_tracks_merged} / {n_tracks} "
          f"({100*n_tracks_merged/n_tracks:.0f}%)" if n_tracks else "    n/a")
    print()
    print(f"  VECTOR ACCURACY (real movement sessions where the map would actually draw a line):")
    print(f"    {vector_would_draw} / {len(movement_sessions)} "
          f"({100*vector_would_draw/len(movement_sessions):.0f}%)" if movement_sessions else "    n/a")

    if verbose:
        print("\n--- split sessions (1 real target landed on >1 track) ---")
        for s in scored:
            tids = session_track_sets[s["session_id"]]
            if len(tids) > 1:
                print(f"  {s['session_id']} (conf={s['confidence']}, "
                      f"{len(s['message_keys'])} msgs) -> tracks {sorted(tids)}")

        print("\n--- merged tracks (>1 real target landed on the same track) ---")
        for tid, sess_ids in track_to_sessions.items():
            if len(sess_ids) > 1:
                print(f"  track {tid} <- sessions {sorted(sess_ids)}")

        print("\n--- unmatched messages per session (no rule-parser event at all) ---")
        for sid, unmatched in session_unmatched.items():
            if unmatched:
                print(f"  {sid}: message_keys {unmatched}")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

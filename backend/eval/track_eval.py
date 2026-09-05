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

The exhaustive per-window ground truth (eval/ground_truth_kyiv_2026-09.json,
plan .claude/plans/target-fanout.md §4.1) is scored by `--gt FILE`: counters,
not fractions — foreign events in labeled tracks, split sessions, the share of
grouping decisions per tier — gated by `_meta.gates` of the file when present.
`--json PATH` dumps the counters for eval/sweep_rebuilds.sh.

    DATABASE_URL="sqlite+aiosqlite:///./copy.db" .venv/bin/python eval/track_eval.py --gt eval/ground_truth_kyiv_2026-09.json [--verbose] [--json out.json]
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import District, RawMessage, Source, Threat, ThreatEvent  # noqa: E402
from app.parsing import DistrictMatcher, parse_message  # noqa: E402

GT_FILE = Path(__file__).parent / "ground_truth_sessions.json"

# Floors, not targets — set just under the measured numbers so ordinary noise
# (the labeled window drifts as the channels post; see _meta in the ground-truth
# file) doesn't cry wolf, while a real tracking regression does. Recorded
# 2026-08-21: scored 57/74, session purity 74%, track purity 97%, vector 70%.
MIN_SCORED_SESSIONS = 52
MIN_SESSION_PURITY = 0.68
MIN_TRACK_PURITY = 0.93
MIN_VECTOR_ACCURACY = 0.64


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
        districts = list(await s.scalars(select(District)))
        raws = list(await s.scalars(select(RawMessage)))
        threats = list(await s.scalars(select(Threat)))

    name_by_source_id = {src.id: src.name for src in sources}
    # The city-wide sentinel is the "attack on the city" banner — inherently
    # multi-target, not a per-target track. A terse pulse («Увага ракета!»)
    # corroborating it makes no claim about target identity, so city-scope
    # tracks are excluded from session attribution (same rationale as the
    # stand-down bookkeeping events below).
    city_track_ids = {t.id for t in threats if t.scope == "city"}

    # A stand-down message («Дорозвідка!», «Чисто!») fans a CLOSING event onto
    # every open track — bookkeeping so the feed shows why tracks ended, not a
    # localization claim. Counting those tracks would "split" any session that
    # contains its own stand-down across every track open at that moment, so
    # events born from a lost-signal message are excluded from attribution.
    matcher = DistrictMatcher(districts)
    text_by_key: dict[tuple[int, int], str] = {
        (r.source_id, r.message_id): r.text
        for r in raws
        if r.source_id is not None and r.message_id is not None
    }
    lost_keys = {
        key for key, text in text_by_key.items()
        if parse_message(text, matcher).lost_signal
    }

    key_to_threat_ids: dict[tuple[str, int], set[int]] = defaultdict(set)
    for e in events:
        name = name_by_source_id.get(e.source_id)
        if name is None or e.source_message_id is None:
            continue
        if (e.source_id, e.source_message_id) in lost_keys:
            continue
        if e.threat_id in city_track_ids:
            continue
        key_to_threat_ids[(name, e.source_message_id)].add(e.threat_id)
    return key_to_threat_ids


async def _load_events():
    async with SessionLocal() as s:
        sources = list(await s.scalars(select(Source)))
        events = list(await s.scalars(select(ThreatEvent)))
        threats = {t.id: t for t in await s.scalars(select(Threat))}
    name_by_source_id = {src.id: src.name for src in sources}
    rows = []
    for e in events:
        t = threats.get(e.threat_id)
        if t is None or t.scope == "city":
            continue
        name = name_by_source_id.get(e.source_id)
        key = (name, e.source_message_id) if name and e.source_message_id is not None else None
        rows.append((e.threat_id, key, e.attached_by, t.target_type))
    return rows


GT_COUNTERS = (
    "sessions", "unscored_sessions", "split_sessions", "extra_tracks", "labeled_tracks",
    "contaminated_tracks", "foreign_events", "not_a_target_events", "mixed_events",
    "outside_events", "ballistic_events",
)


def score_gt(gt: dict, rows: list) -> dict:
    """Counters for an exhaustive ground truth over event rows
    (threat_id, (source_name, message_id) | None, attached_by, target_type)."""
    label: dict[tuple, str] = {}
    window_of: dict[str, str] = {}
    for sess in gt["sessions"]:
        window_of[sess["session_id"]] = sess["window"]
        for k in sess["message_keys"]:
            label[tuple(k)] = sess["session_id"]
    for m in gt.get("mixed", []):
        label[tuple(m["message_key"])] = "mixed"
    for m in gt.get("not_a_target", []):
        label[tuple(m["message_key"])] = "not_a_target"

    by_track: dict[int, list] = defaultdict(list)
    for tid, key, tier, ttype in rows:
        by_track[tid].append((label.get(key, "outside") if key else "outside", tier, ttype))

    per_window: dict[str, Counter] = defaultdict(Counter)
    session_tracks: dict[str, set[int]] = defaultdict(set)
    track_sessions: dict[int, set[str]] = {}
    tiers: Counter = Counter()
    for tid, evs in by_track.items():
        sessions = Counter(lbl for lbl, _, _ in evs if lbl in window_of)
        if not sessions:
            continue
        majority = sessions.most_common(1)[0][0]
        w = window_of[majority]
        track_sessions[tid] = set(sessions)
        for sid in sessions:
            session_tracks[sid].add(tid)
        c = per_window[w]
        c["labeled_tracks"] += 1
        if len(sessions) > 1:
            c["contaminated_tracks"] += 1
        for lbl, tier, ttype in evs:
            if lbl in window_of and lbl != majority:
                c["foreign_events"] += 1
            elif lbl == "not_a_target":
                c["not_a_target_events"] += 1
            elif lbl == "mixed":
                c["mixed_events"] += 1
            elif lbl == "outside":
                c["outside_events"] += 1
            if lbl in window_of or lbl in ("mixed", "not_a_target"):
                tiers[tier or "null"] += 1
                if ttype == "ballistic":
                    c["ballistic_events"] += 1
    for sess in gt["sessions"]:
        c = per_window[sess["window"]]
        n = len(session_tracks.get(sess["session_id"], ()))
        c["sessions"] += 1
        if n == 0:
            c["unscored_sessions"] += 1
        elif n > 1:
            c["split_sessions"] += 1
            c["extra_tracks"] += n - 1
    total: Counter = Counter()
    for c in per_window.values():
        total.update(c)
    return {
        "windows": {w: {k: c[k] for k in GT_COUNTERS} for w, c in sorted(per_window.items())},
        "total": {k: total[k] for k in GT_COUNTERS},
        "tiers": dict(tiers),
        "split_detail": {
            sid: sorted(t) for sid, t in session_tracks.items() if len(t) > 1
        },
        "contaminated_detail": {
            tid: sorted(ss) for tid, ss in track_sessions.items() if len(ss) > 1
        },
    }


def run_gt(gt_path: Path, verbose: bool, json_out: Path | None) -> int:
    gt = json.loads(gt_path.read_text("utf-8"))
    result = score_gt(gt, asyncio.run(_load_events()))
    cols = GT_COUNTERS
    short = ("sess", "unsc", "split", "+trk", "trks", "contam", "foreign", "n_a_t", "mixed",
             "outside", "ballist")
    print(f"\n=== GT EVAL — {gt_path.name}: {len(gt['sessions'])} sessions ===\n")
    print(f"{'window':<8}" + "".join(f"{h:>8}" for h in short))
    for w, c in list(result["windows"].items()) + [("TOTAL", result["total"])]:
        print(f"{w:<8}" + "".join(f"{c.get(k, 0):>8}" for k in cols))
    tiers = result["tiers"]
    n = sum(tiers.values()) or 1
    print("\n  grouping tier of labeled events: " + ", ".join(
        f"{k} {v} ({100 * v / n:.0f}%)" for k, v in sorted(tiers.items(), key=lambda kv: -kv[1])))
    if verbose:
        print("\n--- split sessions ---")
        for sid, tids in result["split_detail"].items():
            print(f"  {sid} -> tracks {tids}")
        print("\n--- contaminated tracks ---")
        for tid, sids in result["contaminated_detail"].items():
            print(f"  track {tid} <- {sids}")
    if json_out is not None:
        json_out.write_text(json.dumps(result, ensure_ascii=False, indent=1))
    gates = gt.get("_meta", {}).get("gates") or {}
    failures = [
        f"{k} {result['total'].get(k, 0)} > {limit}"
        for k, limit in gates.items()
        if result["total"].get(k, 0) > limit
    ]
    if failures:
        print("  REGRESSION: " + "; ".join(failures))
        return 1
    print("  gates: " + (", ".join(f"{k} <= {v}" for k, v in gates.items()) if gates else "none recorded"))
    return 0


def main() -> int:
    verbose = "--verbose" in sys.argv
    if "--gt" in sys.argv:
        json_out = Path(sys.argv[sys.argv.index("--json") + 1]) if "--json" in sys.argv else None
        return run_gt(Path(sys.argv[sys.argv.index("--gt") + 1]), verbose, json_out)
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
    print("  SESSION PURITY (1 real target -> 1 pipeline track):")
    print(f"    pure (correctly one track):   {n_pure} / {n_scored} "
          f"({100*n_pure/n_scored:.0f}%)" if n_scored else "    n/a")
    print(f"    split across multiple tracks: {n_split} / {n_scored} "
          f"({100*n_split/n_scored:.0f}%)" if n_scored else "    n/a")
    print()
    print("  TRACK PURITY (1 pipeline track -> 1 real target, the mega-track check):")
    print(f"    pure (only one real target):     {n_tracks_pure} / {n_tracks} "
          f"({100*n_tracks_pure/n_tracks:.0f}%)" if n_tracks else "    n/a")
    print(f"    merged (2+ real targets in one):  {n_tracks_merged} / {n_tracks} "
          f"({100*n_tracks_merged/n_tracks:.0f}%)" if n_tracks else "    n/a")
    print()
    print("  VECTOR ACCURACY (real movement sessions where the map would actually draw a line):")
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

    # --- Gate ---------------------------------------------------------------
    # Without this the script only PRINTED numbers, so "no regression" meant a
    # human remembering last week's percentages. Now it exits non-zero, which is
    # what tests/test_track_eval.py asserts on.
    failures: list[str] = []

    def check(label: str, value: float, floor: float, fmt: str = "{:.0%}") -> None:
        if value < floor:
            failures.append(f"{label} {fmt.format(value)} < {fmt.format(floor)}")

    check("scored sessions", len(scored), MIN_SCORED_SESSIONS, "{:.0f}")
    if scored:
        check("session purity", n_pure / len(scored), MIN_SESSION_PURITY)
    if n_tracks:
        check("track purity", n_tracks_pure / n_tracks, MIN_TRACK_PURITY)
    if movement_sessions:
        check("vector accuracy", vector_would_draw / len(movement_sessions), MIN_VECTOR_ACCURACY)

    if failures:
        print("  REGRESSION: " + "; ".join(failures))
        print()
        return 1

    print("  all track-level floors met")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Target-type accuracy eval: how often does a sighting end up with the RIGHT
weapon type, and what does each tier of the type stack contribute?

The label comes from `eval/ground_truth_sessions.json` — each hand-labeled real
target session carries a `target_type`, so every message in that session is a
labeled example of "a message about a <type> target". 70 of the 74 sessions are
typed, which is the biggest labeled type set we have.

Two things are measured, separately, because they fail differently:

  * COVERAGE — did the message get a type at all? An untyped sighting is a grey
    dot on the map with the generic stale window. This is where the pipeline
    bleeds: 79% of localizable sightings state no type in their own text.
  * ACCURACY — of the ones that got a type, how many got the right one? A wrong
    weapon icon is worse than a grey one, so this is the number that gates
    letting anything new (i.e. the LLM) write a type.

Accuracy is reported twice, and the pair matters. The ground-truth label is
per-SESSION and coarser than the messages in it: a session labeled `jet_drone`
contains callouts that say plain «БПЛА», and one labeled `missile` contains
«спуск балістики!». Scored strictly, the rules "miss" 87 of 104 such messages
while reading them exactly right — so `exact` is a floor, not a verdict, and
`family` (drone = shahed/jet_drone vs missile = missile/ballistic) is the one
that tracks what a viewer actually sees: shape, vector behaviour and stale
window all follow the family. Read `exact` as subtype precision, `family` as
"did we confuse a drone with a missile", which is the failure that matters.

Baseline (always): the rules plus the per-channel inheritance window. The
incident-prior tier is NOT simulated — it needs live incident state — so the
baseline here is a floor for the real pipeline, not an exact replica.

    cd backend
    DATABASE_URL="sqlite+aiosqlite:///./eval_backfill.db" .venv/bin/python eval/type_eval.py [--verbose]

With `--llm` it additionally runs app/parsing/type_llm.py over the messages the
baseline left untyped, using the same cross-channel context the live pipeline
builds. That one COSTS MONEY (~$0.0017/message on Haiku 4.5); the run prints the
estimate and asks for `--yes` before spending anything. `--limit N` samples.

Recorded 2026-08-23 (584 labeled messages, full --llm run, $0.27):

    tier 1 (message text)        coverage 24.3%   exact 59.2%   family 97.2%
    + tier 2 (channel window)    coverage 40.9%   exact 56.5%   family 93.7%
    tier 4 (LLM + context)       coverage 89.2%   exact 66.0%   family 98.6%
    full stack (with LLM)        coverage 65.1%   exact 60.0%   family 95.5%

Two things to read off that table. The classifier types 141 of the 158 messages
nothing else could — coverage 40.9% -> 65.1% — and its family accuracy (98.6%)
is HIGHER than the tier it extends, so switching it on raises whole-stack family
accuracy from 93.7% to 95.5% instead of trading accuracy for coverage. Not CI-
gated: it needs eval_backfill.db, and the --llm arm costs money.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import District, RawMessage, Source  # noqa: E402
from app.parsing import DistrictMatcher, parse_message  # noqa: E402
from app.pipeline.ingest.context import _note_and_inherit_type, _recent_type  # noqa: E402
from app.pipeline.ingest.type_context import build_type_context  # noqa: E402

GT_FILE = Path(__file__).parent / "ground_truth_sessions.json"

# Haiku 4.5, for the cost estimate the --llm run prints before spending.
_EST_COST_PER_CALL = 0.0017


async def _replay_baseline() -> dict[tuple[str, int], dict]:
    """Replay every stored message chronologically through the rule parser and
    the per-channel type-inheritance window, exactly as ingest does, and return
    what each message ended up with, keyed by (source_name, telegram id).

    Chronological order and the shared `_recent_type` map are the point: the
    inheritance tier is stateful, so scoring it message-by-message in isolation
    would report the rules' coverage, not the pipeline's.
    """
    _recent_type.clear()
    async with SessionLocal() as s:
        districts = list(await s.scalars(select(District)))
        sources = {src.id: src.name for src in await s.scalars(select(Source))}
        raws = list(await s.scalars(select(RawMessage).order_by(RawMessage.event_time)))
    matcher = DistrictMatcher(districts)
    out: dict[tuple[str, int], dict] = {}
    for r in raws:
        parsed = parse_message(r.text or "", matcher)
        stated = parsed.target_type
        _note_and_inherit_type(parsed, r.source_id, r.event_time, None)
        name = sources.get(r.source_id)
        if name is None or r.message_id is None:
            continue
        out[(name, r.message_id)] = {
            "raw_id": r.id,
            "text": r.text or "",
            "when": r.event_time,
            "source": name,
            "stated": stated,                    # tier 1: the message's own words
            "baseline": parsed.target_type,      # tier 1 + tier 2 (channel window)
            "sighting": bool(parsed.districts) or parsed.citywide,
        }
    return out


# drone vs missile — the split the map actually renders (marker shape, whether a
# vector is drawn, the per-type stale window).
_FAMILY = {"shahed": "drone", "jet_drone": "drone",
           "missile": "missile", "ballistic": "missile"}


def _report(title: str, rows: list[tuple[str, str]]) -> None:
    total = len(rows)
    if not total:
        print(f"  {title:28s} —")
        return
    typed = [(label, p) for label, p in rows if p != "unknown"]
    exact = sum(1 for label, p in typed if p == label)
    family = sum(1 for label, p in typed if _FAMILY.get(p) == _FAMILY.get(label))
    n = len(typed)
    print(f"  {title:28s} coverage {len(typed) / total:6.1%} ({n}/{total})   "
          f"exact {exact / n if n else 0:6.1%}   family {family / n if n else 0:6.1%}")


async def _run_llm(cases: list[dict], verbose: bool) -> list[tuple[str, str]]:
    """Classify the still-untyped labeled messages with the real classifier and
    the real context builder. Returns (label, predicted) pairs."""
    from app.parsing.type_llm import llm_target_type

    rows: list[tuple[str, str]] = []
    spend = 0.0
    async with SessionLocal() as s:
        for case in cases:
            context = await build_type_context(
                s, case["when"], exclude_raw_id=case["raw_id"]
            )
            verdict, usage = await llm_target_type(case["text"], context, case["source"])
            if usage is not None:
                spend += usage.cost_usd
            predicted = "unknown"
            if verdict is not None and verdict.usable:
                predicted = verdict.target_type
            rows.append((case["label"], predicted))
            if verbose:
                mark = "ok " if predicted == case["label"] else ("—  " if predicted == "unknown" else "MISS")
                ev = verdict.evidence if verdict else "-"
                conf = f"{verdict.confidence:.2f}" if verdict else "-"
                print(f"    {mark} want={case['label']:10s} got={predicted:10s} "
                      f"{ev:8s} {conf}  | {' '.join(case['text'].split())[:60]}")
    print(f"\n  LLM spend this run: ${spend:.4f} over {len(cases)} calls "
          f"(${spend / max(1, len(cases)):.6f}/call)")
    return rows


def main() -> int:
    verbose = "--verbose" in sys.argv
    use_llm = "--llm" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    gt = json.loads(GT_FILE.read_text("utf-8"))
    sessions = [s for s in gt["sessions"] if s.get("target_type") not in (None, "unknown")]
    baseline = asyncio.run(_replay_baseline())

    labeled: list[dict] = []
    missing = 0
    for sess in sessions:
        for key in sess["message_keys"]:
            row = baseline.get(tuple(key))
            if row is None:            # the DB was rebuilt from a different window
                missing += 1
                continue
            labeled.append({**row, "label": sess["target_type"], "session": sess["session_id"]})

    print(f"\n=== Target-type eval — {len(labeled)} labeled messages "
          f"from {len(sessions)} typed sessions ===")
    if missing:
        print(f"  ({missing} labeled messages not in this DB — rebuild eval_backfill.db)")
    print(f"  label mix: {dict(Counter(c['label'] for c in labeled))}\n")

    _report("tier 1 (message text)", [(c["label"], c["stated"]) for c in labeled])
    _report("+ tier 2 (channel window)", [(c["label"], c["baseline"]) for c in labeled])

    # The classifier's own beat: sightings the earlier tiers left untyped. This
    # is the population the live gate hands it (minus the incident prior, which
    # this replay can't simulate), so scoring it separately is what says whether
    # the LLM is adding types or just re-stating what we already had.
    untyped = [c for c in labeled if c["baseline"] == "unknown" and c["sighting"]]
    print(f"\n  still-untyped sightings: {len(untyped)} "
          f"({len(untyped) / max(1, len(labeled)):.0%} of labeled)")
    by_session = defaultdict(int)
    for c in untyped:
        by_session[c["session"]] += 1
    if verbose:
        for sess, n in sorted(by_session.items(), key=lambda kv: -kv[1])[:10]:
            print(f"    {n:3d}  {sess}")

    if not use_llm:
        print(f"\n  Add --llm to score the classifier on those {len(untyped)} "
              f"(~${len(untyped) * _EST_COST_PER_CALL:.2f}).")
        return 0

    cases = untyped[:limit] if limit else untyped
    if not settings.anthropic_api_key:
        print("\n  ANTHROPIC_API_KEY is unset — nothing to run.")
        return 1
    if "--yes" not in sys.argv:
        print(f"\n  Would spend ~${len(cases) * _EST_COST_PER_CALL:.2f} on "
              f"{len(cases)} calls. Re-run with --yes to do it.")
        return 0

    print(f"\n=== LLM classifier on {len(cases)} untyped sightings ===")
    rows = asyncio.run(_run_llm(cases, verbose))
    print()
    _report("tier 4 (LLM + context)", rows)
    # And what the whole stack would look like with it switched on.
    scored_ids = {c["raw_id"] for c in cases}
    combined = [(c["label"], c["baseline"]) for c in labeled if c["raw_id"] not in scored_ids]
    combined += rows
    _report("full stack (with LLM)", combined)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Mechanical pass over a Kyiv Live Radar /raw feed export.

Counts what can be counted so the reading pass can spend its attention on
judgement instead of arithmetic. Every number here is a POINTER, not a verdict:
"7 tracks in 2 minutes" is normal for a ballistic salvo and pathological for one
drone, and only the message texts can tell you which.

Pure stdlib and DB-free on purpose — it runs on an export file with plain
`python3`, no venv, so it also works on an export someone mailed you.

    python3 feed_report.py export.json
    python3 feed_report.py export.json --texts   # include message text samples
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# Fields added to the export in 2026-08. An older dump simply won't have them;
# every section degrades to "not available" rather than crashing, since old
# exports are still worth analysing.
NEWER_FIELDS = ("suppressed_by", "parsed", "ingested_at", "reply_parent_raw_id")


def _load(path: Path) -> list[dict]:
    data = json.loads(path.read_text("utf-8"))
    if isinstance(data, dict):
        data = data.get("messages", [])
    if not isinstance(data, list):
        sys.exit("expected a list of messages, or an export envelope with .messages")
    return data


def _time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _pct(n: int, total: int) -> str:
    return f"{100 * n / total:4.0f}%" if total else "   -"


def _table(title: str, counter: Counter, total: int) -> None:
    print(f"\n## {title}")
    if not counter:
        print("(none)")
        return
    width = max(len(str(k)) for k in counter)
    for key, n in counter.most_common():
        print(f"  {str(key):<{width}}  {n:4}  {_pct(n, total)}")


def section_outcomes(messages: list[dict]) -> None:
    total = len(messages)
    _table("Outcomes", Counter(m.get("outcome") or "?" for m in messages), total)

    reasons = Counter(m["suppressed_by"] for m in messages if m.get("suppressed_by"))
    if reasons:
        _table("Suppression rule that fired", reasons, total)
    else:
        print("\n## Suppression rule that fired\n(export predates `suppressed_by`)")

    per_source: dict[str, Counter] = defaultdict(Counter)
    for m in messages:
        produced = bool(m.get("events")) or m.get("notice_id") is not None
        per_source[m.get("source_name") or "?"]["surfaced" if produced else "silent"] += 1
    print("\n## Per channel (surfaced = became an event or a notice)")
    for name, c in sorted(per_source.items(), key=lambda kv: -sum(kv[1].values())):
        n = sum(c.values())
        print(f"  {name:<28} {n:4} msgs   surfaced {c['surfaced']:3} ({_pct(c['surfaced'], n)})")


def section_llm(messages: list[dict]) -> None:
    """Which of the two LLM paths spent money, and what it bought.

    The distinction matters: the inline fallback (resolve.py::should_fallback)
    and the async triage engine (triage.py::should_triage) select DIFFERENT
    message classes, so a fix aimed at the wrong one changes nothing. A row with
    a triage_state came through triage."""
    called = [m for m in messages if m.get("llm_attempted")]
    if not called:
        print("\n## LLM\n(no calls in this window)")
        return
    cost = sum(m.get("llm_cost_usd") or 0.0 for m in called)
    inline = [m for m in called if not m.get("triage_state")]
    print(f"\n## LLM — {len(called)} call(s) of {len(messages)} msgs, ${cost:.4f} total")
    print(f"  inline fallback: {len(inline)}   via triage: {len(called) - len(inline)}")
    verdicts = Counter((m.get("llm_response") or {}).get("category", "?") for m in called)
    _table("LLM category verdicts", verdicts, len(called))
    wasted = [m for m in called
              if (m.get("llm_response") or {}).get("category") in ("noise", "?")
              and not m.get("events")]
    if wasted:
        spent = sum(m.get("llm_cost_usd") or 0.0 for m in wasted)
        print(f"\n  {len(wasted)} call(s) returned nothing usable (${spent:.4f}). Ids: "
              + ", ".join(str(m["id"]) for m in wasted))
        print("  -> for each, ask whether a deterministic rule could have known that")
        print("     for free (an ancestor already suppressed, an obvious meta-post).")


def section_ingest_order(messages: list[dict]) -> None:
    """Out-of-order storage is the fingerprint of a reconnect backfill, and the
    root cause of split tracks and post-відбій phantom incidents."""
    print("\n## Ingestion order")
    rows = [m for m in messages if _time(m.get("event_time"))]
    rows.sort(key=lambda m: m["id"])
    late = []
    for prev, cur in zip(rows, rows[1:]):
        if _time(cur["event_time"]) < _time(prev["event_time"]):
            gap = (_time(prev["event_time"]) - _time(cur["event_time"])).total_seconds() / 60
            late.append((cur, gap))
    if late:
        print(f"  {len(late)} message(s) stored AFTER a newer one — backfill replay:")
        for m, gap in late[:10]:
            print(f"    raw {m['id']} (msg {m.get('message_id')}) posted {m['event_time']}"
                  f" — {gap:.0f} min behind the row before it")
    else:
        print("  storage order matches posting order (no backfill replay in this window)")

    lags = []
    for m in messages:
        posted, stored = _time(m.get("event_time")), _time(m.get("ingested_at"))
        if posted and stored:
            lags.append(((stored - posted).total_seconds() / 60, m))
    if lags:
        lags.sort(key=lambda pair: pair[0], reverse=True)
        worst = [(lag, m) for lag, m in lags if lag > 5][:10]
        print(f"\n  ingestion lag available for {len(lags)}/{len(messages)} rows"
              + (f"; {len(worst)} over 5 min:" if worst else "; all under 5 min"))
        for lag, m in worst:
            print(f"    raw {m['id']}: stored {lag:.0f} min after it was posted")
    else:
        print("\n  (export predates `ingested_at` — lag can only be inferred from id order)")


def section_reply_chains(messages: list[dict]) -> None:
    """A reply whose parent we never stored (or stored later) cannot thread, and
    reply-threading is the strongest track-grouping signal there is."""
    print("\n## Reply chains")
    by_key = {(m.get("source_id"), m.get("message_id")): m for m in messages}
    replies = [m for m in messages if m.get("reply_to_message_id")]
    if not replies:
        print("  no replies in this window")
        return
    broken = []
    for m in replies:
        if "reply_parent_raw_id" in m:
            if m.get("reply_parent_raw_id") is None:
                broken.append((m, "parent never stored"))
            elif m["reply_parent_raw_id"] > m["id"]:
                broken.append((m, "parent stored AFTER this reply"))
            continue
        parent = by_key.get((m.get("source_id"), m["reply_to_message_id"]))
        if parent is None:
            broken.append((m, "parent not in this export (may exist in the DB)"))
        elif parent["id"] > m["id"]:
            broken.append((m, "parent stored AFTER this reply"))
    print(f"  {len(replies)} reply/replies, {len(broken)} that could not thread"
          + (":" if broken else ""))
    for m, why in broken[:10]:
        print(f"    raw {m['id']} -> msg {m['reply_to_message_id']}: {why}")


def section_tracks(messages: list[dict]) -> None:
    """Fan-out and type churn — the two shapes that mean the tracker got it
    wrong. Read them against the texts: several simultaneous ballistic impacts
    SHOULD be several tracks; one drone narrated across districts should not."""
    print("\n## Tracks")
    events = [(m, e) for m in messages for e in m.get("events", [])]
    if not events:
        print("  no events in this window")
        return
    by_track: dict[int, list[tuple[dict, dict]]] = defaultdict(list)
    for m, e in events:
        by_track[e["threat_id"]].append((m, e))
    by_incident: dict[object, set[int]] = defaultdict(set)
    for m, e in events:
        by_incident[e.get("incident_id")].add(e["threat_id"])
    print(f"  {len(events)} event(s) across {len(by_track)} track(s), "
          f"{len(by_incident)} incident(s)")

    fan = [(inc, tracks) for inc, tracks in by_incident.items() if len(tracks) >= 4]
    if fan:
        print("  incidents that fanned out into several tracks — read their texts before"
              " judging (a ballistic salvo IS many targets; one narrated drone is not):")
    for inc, tracks in sorted(fan, key=lambda kv: -len(kv[1])):
        print(f"    incident {inc}: {len(tracks)} tracks — "
              + ", ".join(f"T{t}" for t in sorted(tracks)[:12]))

    conflicts = {
        tid: types
        for tid, evs in by_track.items()
        if len(types := {e.get("target_type") for _m, e in evs if e.get("target_type")}) > 1
    }
    if conflicts:
        print("\n  tracks whose events disagree on target type:")
        for tid, types in conflicts.items():
            print(f"    T{tid}: {' / '.join(sorted(types))}")

    singles = [m for m, _e in events if len(m.get("events", [])) == 1]
    multi = [m for m in messages if len(m.get("events", [])) > 1]
    print(f"\n  one message -> one event: {len(singles)}; -> several: {len(multi)}")

    districts = Counter(e.get("district_name") for _m, e in events if e.get("district_name"))
    if districts:
        _table("Districts touched", districts, sum(districts.values()))
    else:
        print("\n  (export predates per-event district — re-export to see where events landed)")


def section_texts(messages: list[dict]) -> None:
    """Everything the pipeline said nothing about, for the reading pass. These
    are where false negatives hide — a real sighting the rules never saw."""
    print("\n## Silent messages (no event, no notice)")
    for m in messages:
        if m.get("events") or m.get("notice_id") is not None:
            continue
        parsed = m.get("parsed") or {}
        hint = ""
        if parsed:
            hint = (f"  [type={parsed.get('target_type')} matched={parsed.get('matched')}"
                    f" pulse={parsed.get('target_pulse')}]")
        text = " ".join((m.get("text") or "").split())[:110]
        print(f"  {m['id']:>6} {m.get('outcome', '?'):<24} {text}{hint}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("export", type=Path)
    ap.add_argument("--texts", action="store_true",
                    help="list every message that produced nothing, with its diagnosis")
    args = ap.parse_args()

    messages = _load(args.export)
    if not messages:
        sys.exit("export contains no messages")
    span = [t for t in (_time(m.get("event_time")) for m in messages) if t]
    print(f"# Feed report — {len(messages)} messages")
    if span:
        print(f"  {min(span).isoformat()} .. {max(span).isoformat()}")
    # "Present but null on every row" counts as missing too: an export taken
    # after the migration still has no ingestion times for rows stored before it.
    missing = [f for f in NEWER_FIELDS if all(m.get(f) is None for m in messages)]
    if missing:
        print(f"  NOTE: export lacks {', '.join(missing)} — some sections are limited.")

    section_outcomes(messages)
    section_llm(messages)
    section_ingest_order(messages)
    section_reply_chains(messages)
    section_tracks(messages)
    if args.texts:
        section_texts(messages)


if __name__ == "__main__":
    main()

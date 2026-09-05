#!/usr/bin/env bash
# Nightly grid of FULL swept rebuilds (plan .claude/plans/target-fanout.md §4.1).
#
# Each line of the configs file is one configuration: a name, then env
# assignments (Settings fields, upper-case). For each one the two source DBs are
# copied, rebuilt through the current pipeline with those settings, and scored:
# track_eval --gt (contamination counters, JSON), the legacy track_eval floors
# on eval_backfill.db, and fanout_report. Results land in $OUT/<name>/.
#
#   cd backend
#   eval/sweep_rebuilds.sh eval/sweep_configs.txt kyiv_radar.db [out_dir]
#
# A configs line:  city4_obl12_m03_legacy  ASSOCIATION_RADIUS_KM_CITY=4 ASSOCIATION_RADIUS_KM_OBLAST=12 AMBIGUITY_MARGIN=0.3 STALE_RULE=legacy
set -euo pipefail

CONFIGS=${1:?configs file}
SRC_DB=${2:?source db (a copy of the live one)}
OUT=${3:-eval/sweep_out}
GT=eval/ground_truth_kyiv_2026-09.json
PY=.venv/bin/python
export TELEGRAM_ENABLED=false SIMULATOR_ENABLED=false REPLAY_REAL_DATA=false LLM_TYPE_MODE=off

mkdir -p "$OUT"
while read -r name assigns; do
  [[ -z "$name" || "$name" == \#* ]] && continue
  dir="$OUT/$name"
  mkdir -p "$dir"
  echo "== $name: $assigns"
  cp "$SRC_DB" "$dir/week.db"
  echo "$assigns" > "$dir/config.txt"
  (
    export ${assigns:-SWEEP_NOOP=1}
    DATABASE_URL="sqlite+aiosqlite:///$dir/week.db" $PY scripts/reprocess_raw.py --no-llm > "$dir/rebuild.log" 2>&1
    DATABASE_URL="sqlite+aiosqlite:///$dir/week.db" $PY eval/track_eval.py --gt "$GT" --verbose --json "$dir/gt.json" > "$dir/gt.txt" 2>&1 || true
    DATABASE_URL="sqlite+aiosqlite:///$dir/week.db" $PY eval/fanout_report.py --since 2026-08-28 > "$dir/fanout.txt" 2>&1
    if [[ -f eval_backfill.db ]]; then
      cp eval_backfill.db "$dir/backfill.db"
      DATABASE_URL="sqlite+aiosqlite:///$dir/backfill.db" $PY scripts/reprocess_raw.py --no-llm > "$dir/rebuild_backfill.log" 2>&1 || true
      DATABASE_URL="sqlite+aiosqlite:///$dir/backfill.db" $PY eval/track_eval.py --verbose > "$dir/legacy.txt" 2>&1 || true
    fi
  )
  grep -E "^TOTAL|tier of" "$dir/gt.txt" || true
  grep -E "peak simultaneous" "$dir/fanout.txt" || true
done < "$CONFIGS"

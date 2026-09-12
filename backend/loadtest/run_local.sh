#!/usr/bin/env bash
# Isolated backend for load testing: a COPY of the local DB, no Telegram (the
# live listener holds the session), no LLM spend, no Sentry/Logfire egress.
#
#   ./loadtest/run_local.sh start        # SQLite copy, uvicorn on :8199
#   ./loadtest/run_local.sh start pg     # Postgres in Docker (:5499) filled by a fast replay
#   ./loadtest/run_local.sh stop
set -euo pipefail
cd "$(dirname "$0")/.."

WORK=${RADAR_LT_DIR:-/tmp/radar-lt}
PORT=${RADAR_LT_PORT:-8199}
mkdir -p "$WORK"

common_env=(
  TELEGRAM_ENABLED=false REPLAY_REAL_DATA=false ALERT_ZONES_ENABLED=false
  TRIAGE_ENABLED=false LLM_FALLBACK_ENABLED=false LLM_TYPE_MODE=off
  ANTHROPIC_API_KEY= LOGFIRE_TOKEN= SENTRY_DSN= LOG_JSON=false
)

start_server() {
  env "${common_env[@]}" "$@" nohup .venv/bin/uvicorn app.main:asgi --host 127.0.0.1 --port "$PORT" \
    >"$WORK/server.log" 2>&1 &
  echo $! >"$WORK/server.pid"
  sleep 6
  curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null && echo "server up on :$PORT (pid $(cat "$WORK/server.pid"))"
}

case "${1:-}" in
  start)
    if [[ "${2:-}" == "pg" ]]; then
      url="postgresql+asyncpg://postgres:lt@127.0.0.1:5499/radar"
      docker start radar-lt-pg 2>/dev/null || docker run -d --name radar-lt-pg -e POSTGRES_PASSWORD=lt \
        -e POSTGRES_DB=radar -p 5499:5432 postgres:16-alpine >/dev/null
      sleep 4
      # Fill an empty database with the 871 captured real messages, shifted to "now".
      env "${common_env[@]}" DATABASE_URL="$url" SIMULATOR_ENABLED=false REPLAY_REAL_DATA=true \
        REPLAY_PACING_MIN=0.01 REPLAY_SHIFT_TO_NOW=true timeout 120 .venv/bin/uvicorn app.main:asgi \
        --host 127.0.0.1 --port "$PORT" >"$WORK/replay.log" 2>&1 || true
      start_server DATABASE_URL="$url" SIMULATOR_ENABLED=true
    else
      cp kyiv_radar.db "$WORK/load.db"
      start_server DATABASE_URL="sqlite+aiosqlite:///$WORK/load.db" SIMULATOR_ENABLED=true
    fi
    ;;
  stop)
    [[ -f "$WORK/server.pid" ]] && kill "$(cat "$WORK/server.pid")" 2>/dev/null && echo "server stopped"
    docker stop radar-lt-pg >/dev/null 2>&1 || true
    ;;
  *)
    echo "usage: $0 start [pg] | stop" >&2
    exit 2
    ;;
esac

#!/usr/bin/env bash
# Stop workflow UI started by demo_gold_up.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="${ROOT}/.demo/workflow.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "[OK] No workflow UI pid file — nothing to stop"
  exit 0
fi

PID="$(cat "$PID_FILE")"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID" 2>/dev/null || true
  sleep 0.5
  kill -9 "$PID" 2>/dev/null || true
  echo "[OK] Stopped workflow UI (pid $PID)"
else
  echo "[OK] Workflow UI not running (stale pid $PID)"
fi
rm -f "$PID_FILE"

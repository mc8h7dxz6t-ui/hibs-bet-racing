#!/usr/bin/env bash
# Prep portfolio demo data and start optional workflow UI for buyer walkthroughs.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
# shellcheck source=instpp_bootstrap.sh
source "$(dirname "$0")/instpp_bootstrap.sh"
instpp_bootstrap

DEMO_DIR="${PORTFOLIO_DEMO_DIR:-./data/demo/portfolio}"
PID_FILE="${ROOT}/.demo/workflow.pid"
LOG_FILE="${ROOT}/.demo/workflow.log"
HOST="${INST_WORKFLOW_HOST:-127.0.0.1}"
PORT="${INST_WORKFLOW_PORT:-8790}"

mkdir -p "$DEMO_DIR" "${ROOT}/.demo"

pip install -e ".[dev,instpp]" -q

if [[ ! -f "$DEMO_DIR/compliance.sqlite" ]] || [[ ! -f "$DEMO_DIR/proxy.sqlite" ]]; then
  echo "==> Seeding Compliance + Proxy demo data for workflow UI"
  export SKIP_LIVE="${SKIP_LIVE:-1}"
  ./scripts/demo_compliance_logger.sh \
    "$DEMO_DIR/compliance.sqlite" \
    "$DEMO_DIR/compliance_bundle" \
    "$DEMO_DIR/compliance_bundle.tar"
  ./scripts/demo_proxy_risk.sh \
    "$DEMO_DIR/proxy.sqlite" \
    "$DEMO_DIR/proxy_bundle" \
    "$DEMO_DIR/proxy_bundle.tar"
fi

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE")"
  if kill -0 "$OLD_PID" 2>/dev/null; then
    echo "[OK] Workflow UI already running (pid $OLD_PID) → http://${HOST}:${PORT}"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

export PORTFOLIO_DEMO_DIR="$DEMO_DIR"
export INST_COMPLIANCE_DB="$DEMO_DIR/compliance.sqlite"
export INST_PROXY_DB="$DEMO_DIR/proxy.sqlite"
export INST_EXPORT_DIR="${ROOT}/data/demo/ui_exports"
export INST_WORKFLOW_DEFAULT_TAB="${INST_WORKFLOW_DEFAULT_TAB:-proof}"

nohup "$PYTHON" -m inst_workflow.cli serve \
  --host "$HOST" --port "$PORT" \
  --compliance-db "$INST_COMPLIANCE_DB" \
  --proxy-db "$INST_PROXY_DB" \
  --export-dir "$INST_EXPORT_DIR" \
  --demo-dir "$DEMO_DIR" \
  >"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"

READY=0
for _ in $(seq 1 30); do
  if ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    break
  fi
  if "$PYTHON" -c "
import urllib.request
urllib.request.urlopen('http://${HOST}:${PORT}/', timeout=2)
" 2>/dev/null; then
    READY=1
    break
  fi
  sleep 1
done

if [[ "$READY" == "1" ]]; then
  echo "[OK] Workflow UI → http://${HOST}:${PORT}"
  echo "     Log: $LOG_FILE"
  echo "     Stop: make demo-gold-down"
elif kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "[WARN] Workflow UI process up but HTTP not ready — see $LOG_FILE" >&2
  exit 1
else
  echo "[FAIL] Workflow UI failed to start — see $LOG_FILE" >&2
  exit 1
fi

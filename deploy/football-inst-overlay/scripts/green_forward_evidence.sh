#!/usr/bin/env bash
# Watch forward F1–F9 gates until green or timeout.
#
#   ./scripts/green_forward_evidence.sh
#   ./scripts/green_forward_evidence.sh --seed
#   ./scripts/green_forward_evidence.sh --watch
#   DEPLOY_HOST=87.106.100.52 ./scripts/green_forward_evidence.sh --remote
set -euo pipefail

APP="${DEPLOY_PATH:-$(cd "$(dirname "$0")/.." && pwd)}"
REMOTE=0
SEED=0
WATCH=0
JSON=0
HOST="${DEPLOY_HOST:-}"

for arg in "$@"; do
  case "${arg}" in
    --remote) REMOTE=1 ;;
    --seed) SEED=1 ;;
    --watch) WATCH=1 ;;
    --json) JSON=1 ;;
  esac
done

if [[ -n "${HOST}" ]]; then
  REMOTE=1
fi

run_local() {
  export HOME="${APP}" PYTHONPATH="${APP}/src" HIBS_PRODUCTION=1
  if [[ -x "${APP}/.venv/bin/python3" ]]; then
    PY="${APP}/.venv/bin/python3"
  else
    PY="python3"
  fi
  if [[ "${SEED}" -eq 1 && -f "${APP}/scripts/seed_forward_evidence.sh" ]]; then
    bash "${APP}/scripts/seed_forward_evidence.sh" --pipeline-only || true
  fi
  "${PY}" -c "
import json, sys
from hibs_predictor.forward_evidence import forward_evidence_gates
d = forward_evidence_gates()
if ${JSON}:
    print(json.dumps(d, indent=2, default=str))
else:
    passed = sum(1 for g in d.get('gates', []) if g.get('pass'))
    total = len(d.get('gates', []))
    print('grade:', d.get('evidence_grade'), 'buyer_ready:', d.get('buyer_ready'))
    print('gates:', passed, '/', total, 'matchdays_7d:', d.get('matchdays_7d'))
    for g in d.get('gates', []):
        if not g.get('pass'):
            print(' FAIL', g.get('id'), '-', g.get('message'))
sys.exit(0 if d.get('buyer_ready') else 1)
"
}

if [[ "${REMOTE}" -eq 1 ]]; then
  HOST="${HOST:-87.106.100.52}"
  USER="${DEPLOY_USER:-root}"
  ssh "${USER}@${HOST}" "cd /opt/hibs-bet && DEPLOY_PATH=/opt/hibs-bet bash scripts/green_forward_evidence.sh ${SEED:+--seed} ${WATCH:+--watch} ${JSON:+--json}"
  exit $?
fi

if [[ "${WATCH}" -eq 1 ]]; then
  attempts=0
  while [[ "${attempts}" -lt 48 ]]; do
    if run_local; then
      echo "forward evidence GREEN"
      exit 0
    fi
    attempts=$((attempts + 1))
    echo "Watch round ${attempts}/48 — sleeping 3600s (load dashboard on matchdays)…"
    sleep 3600
  done
  echo "timeout — evidence not green yet (calendar-bound F7–F9)"
  exit 1
fi

run_local

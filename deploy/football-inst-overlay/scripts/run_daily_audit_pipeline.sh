#!/usr/bin/env bash
# Daily audit pipeline — cron target (see deploy/cron-hibs-calibration.sh).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
export HOME="${HOME:-$ROOT}"
export DEPLOY_PATH="${DEPLOY_PATH:-$ROOT}"

LOCK="/var/run/hibs-bet/daily-audit.lock"
mkdir -p /var/run/hibs-bet 2>/dev/null || true

if command -v flock >/dev/null 2>&1; then
  exec 9>"${LOCK}"
  if ! flock -n 9; then
    echo "SKIP: daily audit already running (flock ${LOCK})"
    exit 0
  fi
fi

RC=0
echo "==> run_daily_audit_pipeline $(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [[ "${HIBS_DAILY_AUDIT_SKIP_BUNDLE:-0}" != "1" ]]; then
  if [[ "${HIBS_DAILY_AUDIT_FORCE_REFRESH:-0}" == "1" ]]; then
    export HIBS_FIXTURE_WARM_FORCE_REFRESH=1
  fi
  if ! bash "$ROOT/scripts/run_forward_backfill_plan.sh"; then
    echo "WARN: forward backfill had errors (continuing to pred-log-sync)"
    RC=1
  fi
else
  echo "==> skip bundle warm (HIBS_DAILY_AUDIT_SKIP_BUNDLE=1)"
fi

SYNC_RC=0
python3 -c "
from hibs_predictor.forward_evidence import ensure_audit_db, run_daily_clv_sync
import json
ensure_audit_db()
result = run_daily_clv_sync()
print(json.dumps(result, default=str))
import sys
sys.exit(0 if result.get('ok') else 1)
" || SYNC_RC=$?

if [[ "${SYNC_RC}" -ne 0 ]]; then
  echo "FAIL: pred-log-sync did not complete OK"
  RC=1
fi

if [[ -x "$ROOT/scripts/institutional_failsafe_verify.sh" ]]; then
  bash "$ROOT/scripts/institutional_failsafe_verify.sh" || true
fi

if [[ "${RC}" -eq 0 ]]; then
  echo "==> daily audit pipeline complete"
else
  echo "==> daily audit pipeline finished with errors (exit ${RC})"
fi
exit "${RC}"

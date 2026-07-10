#!/usr/bin/env bash
# Daily audit pipeline — cron target (see cron-hibs-ops-automation.sh).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"

echo "==> run_daily_audit_pipeline $(date -u +%Y-%m-%dT%H:%M:%SZ)"

bash "$ROOT/scripts/run_forward_backfill_plan.sh" || true

python3 -c "
from hibs_predictor.forward_evidence import ensure_audit_db, run_daily_clv_sync
ensure_audit_db()
print(run_daily_clv_sync())
" || true

if [[ -x "$ROOT/scripts/institutional_failsafe_verify.sh" ]]; then
  bash "$ROOT/scripts/institutional_failsafe_verify.sh" || true
fi

echo "==> daily audit pipeline complete"

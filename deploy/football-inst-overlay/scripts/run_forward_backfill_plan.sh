#!/usr/bin/env bash
# Forward evidence backfill: warm fixtures, seed snapshots, pred-log sync, optional price-truth backfill.
# Run on VPS during fixture windows or via cron before verify_football_evidence_gates.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
export HIBS_FIXTURE_WARM_FORCE_REFRESH="${HIBS_FIXTURE_WARM_FORCE_REFRESH:-1}"
export HIBS_AUDIT_ODDS_RETRY="${HIBS_AUDIT_ODDS_RETRY:-1}"

echo "==> run_forward_backfill_plan (football-inst-overlay)"
echo "    deploy_date=${HIBS_EVIDENCE_DEPLOY_DATE:-unset} force_refresh=$HIBS_FIXTURE_WARM_FORCE_REFRESH"

python3 - <<'PY'
import os
from hibs_predictor.forward_evidence import deploy_revision_iso, ensure_audit_db

ensure_audit_db()
print("since_deploy:", deploy_revision_iso())
PY

echo "==> Step 1: warm fixture bundle (force refresh)"
python3 -c "
from hibs_predictor.fixture_warm import warm_fixture_bundle
r = warm_fixture_bundle(force_refresh=True)
print('warm:', r.get('status'), 'fixtures:', r.get('fixture_count', r.get('count')))
" || echo "WARN: fixture warm failed (check API keys / network)"

echo "==> Step 2: seed forward snapshots (dashboard-equivalent)"
if [[ -x "$ROOT/scripts/seed_forward_evidence.sh" ]]; then
  bash "$ROOT/scripts/seed_forward_evidence.sh" || true
else
  python3 -c "
from hibs_predictor.forward_evidence import ensure_audit_db, log_forward_snapshots_from_bundle
ensure_audit_db()
print('snapshots:', log_forward_snapshots_from_bundle())
" || true
fi

echo "==> Step 3: pred-log sync for web"
python3 -c "
try:
    from hibs_predictor.prediction_log import run_pred_log_sync_for_web
    print(run_pred_log_sync_for_web())
except Exception as e:
    print('pred-log sync skip:', e)
" || true

echo "==> Step 4: optional audit price-truth backfill (set HIBS_SKIP_PRICE_TRUTH_BACKFILL=1 to skip)"
if [[ "${HIBS_SKIP_PRICE_TRUTH_BACKFILL:-0}" != "1" ]]; then
  python3 -c "
try:
    from hibs_predictor.price_truth import backfill_audit_price_truth
    print(backfill_audit_price_truth())
except Exception as e:
    print('price-truth backfill skip:', e)
" || true
fi

echo "==> Step 5: gate summary"
if [[ -x "$ROOT/scripts/verify_football_evidence_gates.sh" ]]; then
  bash "$ROOT/scripts/verify_football_evidence_gates.sh" || true
else
  python3 -c "from hibs_predictor.forward_evidence import forward_evidence_gates; import json; print(json.dumps(forward_evidence_gates(), indent=2))"
fi

#!/usr/bin/env bash
# Seed forward audit snapshots (dashboard-equivalent). Use on matchdays or with force refresh in summer gaps.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
export HIBS_FIXTURE_WARM_FORCE_REFRESH="${HIBS_FIXTURE_WARM_FORCE_REFRESH:-1}"
export HIBS_AUDIT_ODDS_RETRY="${HIBS_AUDIT_ODDS_RETRY:-1}"

PIPELINE_ONLY=0
for arg in "$@"; do
  case "${arg}" in
    --pipeline-only) PIPELINE_ONLY=1 ;;
  esac
done

if [[ "${PIPELINE_ONLY}" -eq 1 ]]; then
  python3 -c "
from hibs_predictor.forward_evidence import ensure_audit_db, log_forward_snapshots_from_bundle
ensure_audit_db()
print('snapshots_logged:', log_forward_snapshots_from_bundle())
"
  exit 0
fi

python3 -c "
from hibs_predictor.fixture_warm import warm_fixture_bundle
from hibs_predictor.forward_evidence import ensure_audit_db, log_forward_snapshots_from_bundle
ensure_audit_db()
warm = warm_fixture_bundle(force_refresh=True)
print('warm:', warm.get('status'), warm.get('fixture_count', warm.get('count')))
n = log_forward_snapshots_from_bundle(force_refresh=False)
print('snapshots_logged:', n)
"

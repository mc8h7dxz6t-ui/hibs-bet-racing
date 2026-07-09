#!/usr/bin/env bash
# Seed forward audit snapshots without dashboard login (cron / hands-off).
#
#   bash scripts/seed_forward_evidence.sh
#   bash scripts/seed_forward_evidence.sh --pipeline-only
set -euo pipefail

APP="${DEPLOY_PATH:-$(cd "$(dirname "$0")/.." && pwd)}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"
PIPELINE_ONLY=0
for arg in "$@"; do
  case "${arg}" in
    --pipeline-only) PIPELINE_ONLY=1 ;;
  esac
done

mkdir -p "${LOG_DIR}"
cd "${APP}"

if [[ -x "${APP}/.venv/bin/python3" ]]; then
  PY="${APP}/.venv/bin/python3"
else
  PY="python3"
fi

export HOME="${APP}" PYTHONPATH="${APP}/src" HIBS_PRODUCTION=1

log() { echo "[seed-forward] $(date -u +%H:%M:%S) $*"; }

log "fixture warm"
if [[ -f "${APP}/scripts/warm_football_fixtures.sh" ]]; then
  bash "${APP}/scripts/warm_football_fixtures.sh" || log "warm skipped/failed"
fi

if [[ "${PIPELINE_ONLY}" -eq 0 ]]; then
  log "prediction snapshot pass"
  "${PY}" -c "
from hibs_predictor.cache import Cache
from hibs_predictor.web import _all_fixtures_cache_key, _is_complete_fixture_bundle
from hibs_predictor.prediction_log import log_predictions_from_fixtures, prediction_log_enabled

cache = Cache()
bundle = cache.peek(_all_fixtures_cache_key(include_domestic=False))
if isinstance(bundle, dict) and _is_complete_fixture_bundle(bundle):
    rows = bundle.get('all') or []
    if prediction_log_enabled():
        n = log_predictions_from_fixtures(rows)
        print('logged', n)
    else:
        print('prediction log disabled')
else:
    print('no complete bundle — warm fixtures first')
" || true
fi

log "done"
exit 0

#!/usr/bin/env bash
# Sync Kaggle raceform.db into feature_store (tag + outcomes, no full matrix rebuild).
#
#   sudo bash /opt/hibs-racing/scripts/sync_raceform_baseline.sh
set -euo pipefail

APP="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
DB="${RACEFORM_DB_PATH:-${APP}/data/raceform.db}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-racing}"
LOG="${LOG_DIR}/raceform-sync.log"
PY="${APP}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY="python3"

mkdir -p "${LOG_DIR}"
cd "${APP}"

if [[ ! -f "${DB}" ]]; then
  echo "[raceform-sync] skip — missing ${DB}" | tee -a "${LOG}"
  exit 0
fi

{
  echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) raceform sync ====="
  "${PY}" -m hibs_racing.cli ingest-raceform "${DB}" --sync
} >>"${LOG}" 2>&1

echo "[raceform-sync] ok — see ${LOG}"

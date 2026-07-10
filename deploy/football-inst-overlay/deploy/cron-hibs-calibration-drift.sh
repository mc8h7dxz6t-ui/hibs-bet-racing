#!/usr/bin/env bash
# Calibration drift alert — daily Brier vs baseline check.
#
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-calibration-drift.sh --install
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-calibration-drift.sh --run
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-bet}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"
LOG_FILE="${LOG_DIR}/calibration-drift.log"
MARKER="# hibs-bet: calibration drift"
PY="${APP_ROOT}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY="python3"

usage() {
  echo "Usage: $0 [--print|--install|--run]"
}

run_drift() {
  mkdir -p "${LOG_DIR}"
  {
    echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) calibration drift ====="
    cd "${APP_ROOT}"
    HOME="${APP_ROOT}" PYTHONPATH=src "${PY}" -c "
from hibs_predictor.calibration_drift import drift_summary_dict
import json
d = drift_summary_dict()
print(json.dumps(d, indent=2, default=str))
if d.get('status') == 'red':
    raise SystemExit(1)
"
    echo "===== done ====="
  } >>"${LOG_FILE}" 2>&1
  chown www-data:www-data "${LOG_FILE}" 2>/dev/null || true
}

install_cron() {
  mkdir -p "${LOG_DIR}"
  local existing tmp
  existing="$(crontab -u www-data -l 2>/dev/null || true)"
  existing="$(printf '%s\n' "${existing}" | grep -vF "${MARKER}" | grep -vF 'calibration_drift' || true)"
  tmp="$(mktemp)"
  {
    printf '%s\n' "${existing}"
    echo ""
    echo "${MARKER}"
    echo "20 7 * * * cd ${APP_ROOT} && HOME=${APP_ROOT} bash ${APP_ROOT}/deploy/cron-hibs-calibration-drift.sh --run >> ${LOG_FILE} 2>&1"
  } >"${tmp}"
  crontab -u www-data "${tmp}"
  rm -f "${tmp}"
  echo "Installed calibration drift alert -> ${LOG_FILE}"
}

case "${1:---print}" in
  --install) install_cron ;;
  --run) run_drift ;;
  --print)
    echo "${MARKER}"
    echo "20 7 * * * cd ${APP_ROOT} && HOME=${APP_ROOT} bash ${APP_ROOT}/deploy/cron-hibs-calibration-drift.sh --run >> ${LOG_FILE} 2>&1"
    ;;
  -h|--help) usage ;;
  *) usage; exit 1 ;;
esac

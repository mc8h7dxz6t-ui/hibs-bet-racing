#!/usr/bin/env bash
# Daily football audit + pred-log-sync — F3 cron gate target.
#
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-calibration.sh --install
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-calibration.sh --run
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-bet}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"
AM_LOG="${LOG_DIR}/daily-audit-am.log"
PM_LOG="${LOG_DIR}/daily-audit-pm.log"
FIT_LOG="${LOG_DIR}/calibration-fit.log"
MARKER="# hibs-bet: daily bundle"
PIPELINE="${APP_ROOT}/scripts/run_daily_audit_pipeline.sh"
PY="${APP_ROOT}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY="python3"

usage() {
  echo "Usage: $0 [--print|--install|--run [--pm]|--run-calibration-fit]"
}

run_pipeline() {
  local slot="${1:-am}"
  mkdir -p "${LOG_DIR}" /var/run/hibs-bet
  chown www-data:www-data "${LOG_DIR}" /var/run/hibs-bet 2>/dev/null || true
  local log_file="${AM_LOG}"
  [[ "${slot}" == "pm" ]] && log_file="${PM_LOG}"
  {
    echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) daily audit (${slot}) ====="
    cd "${APP_ROOT}"
    HOME="${APP_ROOT}" DEPLOY_PATH="${APP_ROOT}" PYTHONPATH=src \
      bash "${PIPELINE}"
    echo "===== exit=$? ====="
  } >>"${log_file}" 2>&1
  chown www-data:www-data "${log_file}" 2>/dev/null || true
}

run_calibration_fit() {
  mkdir -p "${LOG_DIR}"
  {
    echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) calibration-fit ====="
    cd "${APP_ROOT}"
    HOME="${APP_ROOT}" PYTHONPATH=src "${PY}" -m hibs_predictor.main calibration-fit
    echo "===== exit=$? ====="
  } >>"${FIT_LOG}" 2>&1
  chown www-data:www-data "${FIT_LOG}" 2>/dev/null || true
}

install_cron() {
  mkdir -p "${LOG_DIR}" /var/run/hibs-bet
  chmod +x "${PIPELINE}" 2>/dev/null || true
  local existing tmp
  existing="$(crontab -u www-data -l 2>/dev/null || true)"
  existing="$(printf '%s\n' "${existing}" | \
    grep -vF "${MARKER}" | \
    grep -vF 'run_daily_audit_pipeline.sh' | \
    grep -vF 'hibs_predictor.main calibration-fit' || true)"
  tmp="$(mktemp)"
  {
    printf '%s\n' "${existing}"
    echo ""
    echo "${MARKER}"
    echo "# Morning audit + pred-log-sync (after 06:25 fixture warm)"
    echo "35 6 * * * cd ${APP_ROOT} && HOME=${APP_ROOT} DEPLOY_PATH=${APP_ROOT} bash ${APP_ROOT}/deploy/cron-hibs-calibration.sh --run >> ${AM_LOG} 2>&1"
    echo "# Evening audit + pred-log-sync (post kick-offs)"
    echo "5 23 * * * cd ${APP_ROOT} && HOME=${APP_ROOT} DEPLOY_PATH=${APP_ROOT} bash ${APP_ROOT}/deploy/cron-hibs-calibration.sh --run --pm >> ${PM_LOG} 2>&1"
    echo "# Weekly league shrink cache"
    echo "0 7 * * 0 cd ${APP_ROOT} && HOME=${APP_ROOT} DEPLOY_PATH=${APP_ROOT} bash ${APP_ROOT}/deploy/cron-hibs-calibration.sh --run-calibration-fit >> ${FIT_LOG} 2>&1"
  } >"${tmp}"
  crontab -u www-data "${tmp}"
  rm -f "${tmp}"
  echo "Installed daily audit crons -> ${AM_LOG}, ${PM_LOG}, ${FIT_LOG}"
}

case "${1:---print}" in
  --install) install_cron ;;
  --run)
    if [[ "${2:-}" == "--pm" ]]; then
      run_pipeline pm
    else
      run_pipeline am
    fi
    ;;
  --run-calibration-fit) run_calibration_fit ;;
  --print)
    echo "${MARKER}"
    echo "35 6 * * * ... cron-hibs-calibration.sh --run"
    echo "5 23 * * * ... cron-hibs-calibration.sh --run --pm"
    echo "0 7 * * 0 ... cron-hibs-calibration.sh --run-calibration-fit"
    ;;
  -h|--help) usage ;;
  *) usage; exit 1 ;;
esac

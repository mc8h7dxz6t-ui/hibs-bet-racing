#!/usr/bin/env bash
# Institutional++ watchdog — daily grades + optional repair.
#
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-institutional-watchdog.sh --install
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-institutional-watchdog.sh --run
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-bet}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"
LOG_FILE="${LOG_DIR}/institutional-watchdog.log"
MARKER="# hibs-bet: institutional++ watchdog"
WATCHDOG="${APP_ROOT}/scripts/institutional_vps_watchdog.sh"

usage() {
  echo "Usage: $0 [--print|--install|--run]"
}

run_watchdog() {
  mkdir -p "${LOG_DIR}"
  {
    echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) institutional watchdog ====="
    sudo HOME="${APP_ROOT}" DEPLOY_PATH="${APP_ROOT}" bash "${WATCHDOG}" --repair
    echo "===== done ====="
  } >>"${LOG_FILE}" 2>&1
  chown www-data:www-data "${LOG_FILE}" 2>/dev/null || true
}

install_cron() {
  mkdir -p "${LOG_DIR}"
  chmod +x "${WATCHDOG}" 2>/dev/null || true
  local existing tmp
  existing="$(crontab -u www-data -l 2>/dev/null || true)"
  existing="$(printf '%s\n' "${existing}" | grep -vF "${MARKER}" | grep -vF 'institutional_vps_watchdog.sh' || true)"
  tmp="$(mktemp)"
  {
    printf '%s\n' "${existing}"
    echo ""
    echo "${MARKER}"
    echo "45 7 * * * sudo bash ${APP_ROOT}/deploy/cron-hibs-institutional-watchdog.sh --run >> ${LOG_FILE} 2>&1"
  } >"${tmp}"
  crontab -u www-data "${tmp}"
  rm -f "${tmp}"
  echo "Installed institutional watchdog -> ${LOG_FILE}"
}

case "${1:---print}" in
  --install) install_cron ;;
  --run) run_watchdog ;;
  --print)
    echo "${MARKER}"
    echo "45 7 * * * sudo bash ${APP_ROOT}/deploy/cron-hibs-institutional-watchdog.sh --run >> ${LOG_FILE} 2>&1"
    ;;
  -h|--help) usage ;;
  *) usage; exit 1 ;;
esac

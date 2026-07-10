#!/usr/bin/env bash
# Hands-off repair cycle — every 30m, flock + rate limits, cron exit 0 on evidence red.
#
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-hands-off.sh --install
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-hands-off.sh --run
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-bet}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"
LOG_FILE="${LOG_DIR}/hands-off-cycle.log"
MARKER="# hibs-bet: hands-off cycle"
CYCLE="${APP_ROOT}/scripts/hands_off_cycle.sh"

usage() {
  echo "Usage: $0 [--print|--install|--run]"
}

run_cycle() {
  mkdir -p "${LOG_DIR}" /var/run/hibs-bet
  if [[ "$(id -u)" -eq 0 ]]; then
    HOME="${APP_ROOT}" DEPLOY_PATH="${APP_ROOT}" bash "${CYCLE}"
  else
    sudo HOME="${APP_ROOT}" DEPLOY_PATH="${APP_ROOT}" bash "${CYCLE}"
  fi
}

install_cron() {
  mkdir -p "${LOG_DIR}" /var/run/hibs-bet
  chmod +x "${CYCLE}" 2>/dev/null || true
  local existing tmp
  existing="$(crontab -u www-data -l 2>/dev/null || true)"
  existing="$(printf '%s\n' "${existing}" | grep -vF "${MARKER}" | grep -vF 'hands_off_cycle.sh' || true)"
  tmp="$(mktemp)"
  {
    printf '%s\n' "${existing}"
    echo ""
    echo "${MARKER}"
    echo "*/30 * * * * sudo bash ${APP_ROOT}/deploy/cron-hibs-hands-off.sh --run >> ${LOG_FILE} 2>&1"
  } >"${tmp}"
  crontab -u www-data "${tmp}"
  rm -f "${tmp}"
  echo "Installed hands-off cycle -> ${LOG_FILE}"
  echo "Ensure: sudo bash ${APP_ROOT}/deploy/install-hibs-cron-sudoers.sh"
}

case "${1:---print}" in
  --install) install_cron ;;
  --run) run_cycle ;;
  --print)
    echo "${MARKER}"
    echo "*/30 * * * * sudo bash ${APP_ROOT}/deploy/cron-hibs-hands-off.sh --run >> ${LOG_FILE} 2>&1"
    ;;
  -h|--help) usage ;;
  *) usage; exit 1 ;;
esac

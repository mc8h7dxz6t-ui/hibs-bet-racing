#!/usr/bin/env bash
# Cron: headless football fixture warm (outside gunicorn — does not wedge :8000).
#
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-football-fixture-warm.sh --install
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-football-fixture-warm.sh --run
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-bet}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"
LOG_FILE="${LOG_DIR}/fixture-warm.log"
MARKER="# hibs-bet: football fixture warm (headless)"
SCRIPT="${APP_ROOT}/scripts/warm_football_fixtures.sh"

usage() {
  echo "Usage: $0 [--print|--install|--run]"
}

run_warm() {
  mkdir -p "${LOG_DIR}" /var/run/hibs-bet
  {
    echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) fixture warm ====="
    HOME="${APP_ROOT}" DEPLOY_PATH="${APP_ROOT}" bash "${SCRIPT}"
  } >>"${LOG_FILE}" 2>&1
  chown www-data:www-data "${LOG_FILE}" 2>/dev/null || true
}

install_cron() {
  mkdir -p "${LOG_DIR}" /var/run/hibs-bet
  chown www-data:www-data "${LOG_DIR}" /var/run/hibs-bet 2>/dev/null || true
  chmod +x "${SCRIPT}" 2>/dev/null || true
  local existing tmp
  existing="$(crontab -u www-data -l 2>/dev/null || true)"
  existing="$(printf '%s\n' "${existing}" | grep -vF "${MARKER}" | grep -vF 'warm_football_fixtures' || true)"
  tmp="$(mktemp)"
  {
    printf '%s\n' "${existing}"
    echo ""
    echo "${MARKER}"
    echo "# Every 3h — skip if bundle fresh on disk"
    echo "20 */3 * * * cd ${APP_ROOT} && HOME=${APP_ROOT} DEPLOY_PATH=${APP_ROOT} bash ${SCRIPT} >> ${LOG_FILE} 2>&1"
    echo "# Morning before daily audit (06:35)"
    echo "25 6 * * * cd ${APP_ROOT} && HOME=${APP_ROOT} DEPLOY_PATH=${APP_ROOT} bash ${SCRIPT} >> ${LOG_FILE} 2>&1"
    echo "# After boot (90s delay)"
    echo "@reboot sleep 90 && cd ${APP_ROOT} && HOME=${APP_ROOT} DEPLOY_PATH=${APP_ROOT} bash ${SCRIPT} >> ${LOG_FILE} 2>&1"
  } >"${tmp}"
  crontab -u www-data "${tmp}"
  rm -f "${tmp}"
  echo "Installed football fixture warm cron -> ${LOG_FILE}"
}

case "${1:---print}" in
  --install) install_cron ;;
  --run) run_warm ;;
  --print)
    echo "${MARKER}"
    echo "20 */3 * * * cd ${APP_ROOT} && HOME=${APP_ROOT} bash ${SCRIPT} >> ${LOG_FILE} 2>&1"
    echo "25 6 * * * cd ${APP_ROOT} && HOME=${APP_ROOT} bash ${SCRIPT} >> ${LOG_FILE} 2>&1"
    echo "@reboot sleep 90 && cd ${APP_ROOT} && HOME=${APP_ROOT} bash ${SCRIPT} >> ${LOG_FILE} 2>&1"
    ;;
  -h|--help) usage ;;
  *) usage; exit 1 ;;
esac

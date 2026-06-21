#!/usr/bin/env bash
# Cron: automated low-source scrape cycle (no API-Sports burn).
#
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-low-source-scrape.sh --install
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-low-source-scrape.sh --run
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-bet}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"
LOG_FILE="${LOG_DIR}/low-source-scrape.log"
MARKER="# hibs-bet: low-source scrape cycle (FDO/FotMob/ESPN)"
SCRIPT="${APP_ROOT}/scripts/warm_low_source_scrape.sh"

usage() {
  echo "Usage: $0 [--print|--install|--run]"
}

run_cycle() {
  mkdir -p "${LOG_DIR}" /var/run/hibs-bet
  {
    echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) low-source scrape ====="
    HOME="${APP_ROOT}" DEPLOY_PATH="${APP_ROOT}" LOG_DIR="${LOG_DIR}" bash "${SCRIPT}"
  } >>"${LOG_FILE}" 2>&1
  chown www-data:www-data "${LOG_FILE}" "${LOG_DIR}/low-source-scrape.json" 2>/dev/null || true
}

install_cron() {
  mkdir -p "${LOG_DIR}" /var/run/hibs-bet
  chmod +x "${SCRIPT}" 2>/dev/null || true
  local existing tmp
  existing="$(crontab -u www-data -l 2>/dev/null || true)"
  existing="$(printf '%s\n' "${existing}" | grep -vF "${MARKER}" | grep -vF 'warm_low_source_scrape' || true)"
  tmp="$(mktemp)"
  {
    printf '%s\n' "${existing}"
    echo ""
    echo "${MARKER}"
    echo "# Every 2h — scrape fixtures + thin rescue; backfill bundle when empty"
    echo "10 */2 * * * cd ${APP_ROOT} && HOME=${APP_ROOT} DEPLOY_PATH=${APP_ROOT} bash ${SCRIPT} >> ${LOG_FILE} 2>&1"
    echo "# After fixture warm (offset 15m)"
    echo "35 */3 * * * cd ${APP_ROOT} && HOME=${APP_ROOT} DEPLOY_PATH=${APP_ROOT} bash ${SCRIPT} >> ${LOG_FILE} 2>&1"
    echo "# Morning before audit"
    echo "40 6 * * * cd ${APP_ROOT} && HOME=${APP_ROOT} DEPLOY_PATH=${APP_ROOT} bash ${SCRIPT} >> ${LOG_FILE} 2>&1"
  } >"${tmp}"
  crontab -u www-data "${tmp}"
  rm -f "${tmp}"
  echo "Installed low-source scrape cron -> ${LOG_FILE}"
}

case "${1:---print}" in
  --install) install_cron ;;
  --run) run_cycle ;;
  --print)
    echo "${MARKER}"
    echo "10 */2 * * * cd ${APP_ROOT} && HOME=${APP_ROOT} bash ${SCRIPT} >> ${LOG_FILE} 2>&1"
    echo "35 */3 * * * cd ${APP_ROOT} && HOME=${APP_ROOT} bash ${SCRIPT} >> ${LOG_FILE} 2>&1"
    echo "40 6 * * * cd ${APP_ROOT} && HOME=${APP_ROOT} bash ${SCRIPT} >> ${LOG_FILE} 2>&1"
    ;;
  -h|--help) usage ;;
  *) usage; exit 1 ;;
esac

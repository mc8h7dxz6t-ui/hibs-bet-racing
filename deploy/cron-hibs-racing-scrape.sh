#!/usr/bin/env bash
# Cron: racing robust scrape cycle (cards + odds + thin rescue).
#
#   sudo bash /opt/hibs-racing/deploy/cron-hibs-racing-scrape.sh --install
#   sudo bash /opt/hibs-racing/deploy/cron-hibs-racing-scrape.sh --run
set -euo pipefail

RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-racing}"
LOG_FILE="${LOG_DIR}/robust-racing-scrape.log"
MARKER="# hibs-racing: robust scrape cycle"
SCRIPT="${RACING}/scripts/warm_racing_scrape.sh"

usage() {
  echo "Usage: $0 [--print|--install|--run]"
}

run_cycle() {
  mkdir -p "${LOG_DIR}" /var/run/hibs-racing
  {
    echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) robust racing scrape ====="
    if [[ ! -f "${SCRIPT}" ]]; then
      echo "ERROR: missing ${SCRIPT}"
      exit 1
    fi
    HOME="${RACING}" HIBS_RACING_DEPLOY_PATH="${RACING}" LOG_DIR="${LOG_DIR}" \
      HIBS_ALWAYS_SCRAPE=1 HIBS_RACING_SCRAPE_FORCE=1 bash "${SCRIPT}"
  } >>"${LOG_FILE}" 2>&1
  chown www-data:www-data "${LOG_FILE}" "${LOG_DIR}/robust-racing-scrape.json" 2>/dev/null || true
}

install_cron() {
  mkdir -p "${LOG_DIR}" /var/run/hibs-racing
  chmod +x "${SCRIPT}" 2>/dev/null || true
  local existing tmp
  existing="$(crontab -u www-data -l 2>/dev/null || true)"
  existing="$(printf '%s\n' "${existing}" | grep -vF "${MARKER}" | grep -vF 'warm_racing_scrape' || true)"
  tmp="$(mktemp)"
  {
    printf '%s\n' "${existing}"
    echo ""
    echo "${MARKER}"
    echo "# Every 2h — max-data cards + odds + thin rescue (always on)"
    echo "20 */2 * * * cd ${RACING} && HOME=${RACING} HIBS_RACING_DEPLOY_PATH=${RACING} HIBS_ALWAYS_SCRAPE=1 HIBS_RACING_SCRAPE_FORCE=1 bash ${SCRIPT} >> ${LOG_FILE} 2>&1"
    echo "# Pre-racing morning pass"
    echo "0 5 * * * cd ${RACING} && HOME=${RACING} HIBS_RACING_DEPLOY_PATH=${RACING} HIBS_ALWAYS_SCRAPE=1 HIBS_RACING_SCRAPE_FORCE=1 bash ${SCRIPT} >> ${LOG_FILE} 2>&1"
  } >"${tmp}"
  crontab -u www-data "${tmp}"
  rm -f "${tmp}"
  echo "Installed racing robust scrape cron -> ${LOG_FILE}"
}

case "${1:---print}" in
  --install) install_cron ;;
  --run) run_cycle ;;
  --print)
    echo "${MARKER}"
    echo "20 */2 * * * cd ${RACING} && HOME=${RACING} bash ${SCRIPT} >> ${LOG_FILE} 2>&1"
    echo "0 5 * * * cd ${RACING} && HOME=${RACING} bash ${SCRIPT} >> ${LOG_FILE} 2>&1"
    ;;
  -h|--help) usage ;;
  *) usage; exit 1 ;;
esac

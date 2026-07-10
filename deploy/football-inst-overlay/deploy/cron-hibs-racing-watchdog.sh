#!/usr/bin/env bash
# Racing ping watchdog — restart hibs-racing if hung (consolidated VPS).
#
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-racing-watchdog.sh --install
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-racing-watchdog.sh --run
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-racing}"
LOG_FILE="${LOG_DIR}/watchdog.log"
MARKER="# hibs-racing: ping watchdog"
PING_URL="${HIBS_RACING_PING_URL:-http://127.0.0.1:5003/api/ping}"

usage() { echo "Usage: $0 [--print|--install|--run]"; }

run_watchdog() {
  mkdir -p "${LOG_DIR}"
  if curl -fsS --max-time 8 "${PING_URL}" >/dev/null 2>&1; then
    exit 0
  fi
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) ping failed — restart hibs-racing" >>"${LOG_FILE}"
  if [[ "$(id -u)" -eq 0 ]]; then
    systemctl restart hibs-racing 2>>"${LOG_FILE}" || true
  fi
}

install_cron() {
  mkdir -p "${LOG_DIR}"
  local existing tmp
  existing="$(crontab -l 2>/dev/null || true)"
  existing="$(printf '%s\n' "${existing}" | grep -vF "${MARKER}" | grep -vF 'cron-hibs-racing-watchdog.sh' || true)"
  tmp="$(mktemp)"
  {
    printf '%s\n' "${existing}"
    echo ""
    echo "${MARKER}"
    echo "*/15 * * * * bash ${APP_ROOT}/deploy/cron-hibs-racing-watchdog.sh --run >> ${LOG_FILE} 2>&1"
  } >"${tmp}"
  crontab "${tmp}"
  rm -f "${tmp}"
  echo "Installed racing watchdog in root crontab -> ${LOG_FILE}"
}

case "${1:---print}" in
  --install) install_cron ;;
  --run) run_watchdog ;;
  --print)
    echo "${MARKER}"
    echo "*/15 * * * * ... cron-hibs-racing-watchdog.sh --run"
    ;;
  -h|--help) usage ;;
  *) usage; exit 1 ;;
esac

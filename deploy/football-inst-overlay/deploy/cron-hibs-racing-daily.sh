#!/usr/bin/env bash
# Racing daily refresh on consolidated VPS (local — no SSH).
#
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-racing-daily.sh --install
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-racing-daily.sh --run
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-racing}"
LOG_FILE="${LOG_DIR}/daily-refresh.log"
MARKER="# hibs-racing: daily refresh"
REFRESH="${RACING}/scripts/daily_refresh.sh"
WRAPPER="${RACING}/scripts/cron_refresh_wrapper.sh"

usage() { echo "Usage: $0 [--print|--install|--run]"; }

run_refresh() {
  mkdir -p "${LOG_DIR}"
  [[ -d "${RACING}" ]] || { echo "ERROR: ${RACING} missing" >&2; exit 1; }
  local runner="${REFRESH}"
  [[ -x "${WRAPPER}" ]] && runner="${WRAPPER}"
  [[ -x "${runner}" ]] || { echo "ERROR: no daily_refresh at ${RACING}" >&2; exit 1; }
  {
    echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) racing daily ====="
    cd "${RACING}"
    HIBS_OBSERVATION_LANE="${HIBS_OBSERVATION_LANE:-1}" HOME="${RACING}" \
      bash "${runner}"
    echo "===== exit=$? ====="
  } >>"${LOG_FILE}" 2>&1
}

install_cron() {
  mkdir -p "${LOG_DIR}"
  local existing tmp
  existing="$(crontab -u www-data -l 2>/dev/null || true)"
  existing="$(printf '%s\n' "${existing}" | grep -vF "${MARKER}" | grep -vF 'cron-hibs-racing-daily.sh' || true)"
  tmp="$(mktemp)"
  {
    printf '%s\n' "${existing}"
    echo ""
    echo "${MARKER}"
    echo "# 06:05 UTC — after football morning audit"
    echo "5 6 * * * cd ${APP_ROOT} && HOME=${RACING} HIBS_RACING_DEPLOY_PATH=${RACING} bash ${APP_ROOT}/deploy/cron-hibs-racing-daily.sh --run >> ${LOG_FILE} 2>&1"
  } >"${tmp}"
  crontab -u www-data "${tmp}"
  rm -f "${tmp}"
  echo "Installed racing daily cron -> ${LOG_FILE}"
}

case "${1:---print}" in
  --install) install_cron ;;
  --run) run_refresh ;;
  --print)
    echo "${MARKER}"
    echo "5 6 * * * ... cron-hibs-racing-daily.sh --run"
    ;;
  -h|--help) usage ;;
  *) usage; exit 1 ;;
esac

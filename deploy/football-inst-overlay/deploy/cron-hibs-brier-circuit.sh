#!/usr/bin/env bash
# Hourly Brier runtime circuit breaker — execution lockout on calibration drift.
#
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-brier-circuit.sh --install
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-brier-circuit.sh --run
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-bet}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"
LOG_FILE="${LOG_DIR}/brier-circuit.log"
MARKER="# hibs-bet: brier circuit breaker (hourly)"
RUNNER="${APP_ROOT}/scripts/run_brier_circuit_breaker.sh"

usage() { echo "Usage: $0 [--print|--install|--run]"; }

run_breaker() {
  [[ -x "${RUNNER}" ]] || chmod +x "${RUNNER}" 2>/dev/null || true
  mkdir -p "${LOG_DIR}"
  {
    echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) brier circuit ====="
    HOME="${APP_ROOT}" DEPLOY_PATH="${APP_ROOT}" bash "${RUNNER}"
    echo "===== done ====="
  } >>"${LOG_FILE}" 2>&1
  chown www-data:www-data "${LOG_FILE}" 2>/dev/null || true
}

install_cron() {
  [[ -f "${RUNNER}" ]] || {
    echo "WARN: ${RUNNER} missing — sync overlay first" >&2
    exit 1
  }
  if [[ -f "${APP_ROOT}/deploy/lib_cron_dedupe.sh" ]]; then
    # shellcheck source=lib_cron_dedupe.sh
    source "${APP_ROOT}/deploy/lib_cron_dedupe.sh"
    if ! hibs_crontab_install_guard www-data 2>/dev/null; then
      echo "WARN: crontab bloated — run crontab-emergency-sports-only.sh first" >&2
      exit 1
    fi
  fi
  local existing tmp
  existing="$(crontab -u www-data -l 2>/dev/null || true)"
  existing="$(printf '%s\n' "${existing}" | grep -vF "${MARKER}" | grep -vF 'run_brier_circuit_breaker.sh' | grep -vF 'cron-hibs-brier-circuit.sh' || true)"
  tmp="$(mktemp)"
  {
    printf '%s\n' "${existing}"
    echo ""
    echo "${MARKER}"
    echo "5 * * * * bash ${APP_ROOT}/deploy/cron-hibs-brier-circuit.sh --run >> ${LOG_FILE} 2>&1"
  } >"${tmp}"
  crontab -u www-data "${tmp}"
  rm -f "${tmp}"
  echo "Installed hourly Brier circuit breaker cron"
}

case "${1:-}" in
  --print) crontab -u www-data -l 2>/dev/null | grep -F "${MARKER}" -A1 || true ;;
  --install) install_cron ;;
  --run) run_breaker ;;
  *) usage; exit 1 ;;
esac

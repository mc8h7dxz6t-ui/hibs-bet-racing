#!/usr/bin/env bash
# Cron: fast infra fallback (football + racing ping) every 5 minutes.
#
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-infra-fallback.sh --install
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-infra-fallback.sh --run
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-bet}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"
LOG_FILE="${LOG_DIR}/infra-fallback.log"
MARKER="# hibs-bet: infra fallback (5m)"
CYCLE="${APP_ROOT}/scripts/vps_infra_fallback_cycle.sh"

usage() { echo "Usage: $0 [--print|--install|--run]"; }

run_cycle() {
  mkdir -p "${LOG_DIR}" /var/run/hibs-bet
  chmod +x "${CYCLE}" 2>/dev/null || true
  HOME="${APP_ROOT}" DEPLOY_PATH="${APP_ROOT}" bash "${CYCLE}"
}

install_cron() {
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
  existing="$(printf '%s\n' "${existing}" | grep -vF "${MARKER}" | grep -vF 'vps_infra_fallback_cycle.sh' | grep -vF 'cron-hibs-infra-fallback.sh' || true)"
  tmp="$(mktemp)"
  {
    printf '%s\n' "${existing}"
    echo ""
    echo "${MARKER}"
    echo "*/5 * * * * sudo bash ${APP_ROOT}/deploy/cron-hibs-infra-fallback.sh --run >> ${LOG_FILE} 2>&1"
  } >"${tmp}"
  crontab -u www-data "${tmp}"
  rm -f "${tmp}"
  echo "Installed infra fallback cron (every 5m)"
}

case "${1:-}" in
  --print) crontab -u www-data -l 2>/dev/null | grep -F "${MARKER}" -A1 || true ;;
  --install) install_cron ;;
  --run) run_cycle ;;
  *) usage; exit 1 ;;
esac

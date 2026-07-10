#!/usr/bin/env bash
# Lightweight infra fallback — probe + repair before heavy hands-off cycle.
# Cron-safe (exit 0). Runs every 5m via cron-hibs-infra-fallback.sh.
#
#   sudo bash /opt/hibs-bet/scripts/vps_infra_fallback_cycle.sh
set -uo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"
LOG_FILE="${LOG_DIR}/infra-fallback.log"

log() { echo "[infra-fallback] $(date -u +%H:%M:%S) $*"; }

mkdir -p "${LOG_DIR}"
[[ "$(id -u)" -eq 0 ]] || { log "skip — not root"; exit 0; }

if command -v flock >/dev/null 2>&1; then
  exec 9>/var/run/hibs-bet/infra-fallback.lock
  mkdir -p /var/run/hibs-bet
  if ! flock -n 9; then
    log "skip — lock held"
    exit 0
  fi
fi

{
  log "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) ====="
  if [[ -f "${APP}/scripts/lib_football_vps_fallback.sh" ]]; then
    # shellcheck source=lib_football_vps_fallback.sh
    source "${APP}/scripts/lib_football_vps_fallback.sh"
    export DEPLOY_PATH="${APP}" HIBS_RACING_DEPLOY_PATH="${RACING}"
    if stack_vps_automation_fallback "${APP}" "${RACING}"; then
      log "stack probe GREEN"
    else
      log "stack probe RED — throttled recovery may have run; see fb-fallback lines above"
    fi
  else
    log "missing lib_football_vps_fallback.sh"
  fi
} >>"${LOG_FILE}" 2>&1

chown www-data:www-data "${LOG_FILE}" 2>/dev/null || true
exit 0

#!/usr/bin/env bash
# Repair empty racing cards on VPS (service + raceform + daily refresh).
#
#   sudo bash /opt/hibs-bet/scripts/vps_racing_repair.sh
#   sudo bash /opt/hibs-bet/scripts/vps_racing_repair.sh --diagnose-only
set -euo pipefail

APP="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
BET="${HIBS_BET_DEPLOY_PATH:-/opt/hibs-bet}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-racing}"
DIAG_ONLY=0

for arg in "$@"; do
  [[ "${arg}" == "--diagnose-only" ]] && DIAG_ONLY=1
done

log() { echo "[racing-repair] $*"; }
warn() { echo "[racing-repair] WARN: $*" >&2; }

[[ "$(id -u)" -eq 0 ]] || { echo "run as root: sudo bash $0" >&2; exit 1; }

if [[ ! -d "${APP}" ]]; then
  echo "ERROR: ${APP} missing — deploy hibs-racing first:" >&2
  echo "  sudo bash ${BET}/scripts/link_racing_production.sh" >&2
  echo "  or rsync from old VPS: ${BET}/deploy/ops-migrate-from-old-vps.sh" >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${APP}/data"
export HIBS_RACING_DEPLOY_PATH="${APP}"
export HIBS_BET_DEPLOY_PATH="${BET}"

log "diagnose (before)"
if [[ -f "${BET}/scripts/vps_racing_diagnose_cards.sh" ]]; then
  bash "${BET}/scripts/vps_racing_diagnose_cards.sh" || true
elif [[ -f "${BET}/scripts/diagnose_racing_vps.sh" ]]; then
  bash "${BET}/scripts/diagnose_racing_vps.sh" || true
fi

if [[ "${DIAG_ONLY}" -eq 1 ]]; then
  exit 0
fi

# shellcheck source=lib_racing_vps_probe.sh
source "${BET}/scripts/lib_racing_vps_probe.sh"

if ! racing_vps_repair_raceform_env "${APP}"; then
  echo "" >&2
  echo "BLOCKED: raceform.db missing at $(racing_vps_canonical_raceform "${APP}")" >&2
  echo "From old VPS (.73):" >&2
  echo "  rsync -avz root@77.68.89.73:/opt/hibs-racing/data/ ${APP}/data/" >&2
  echo "  rsync -avz root@77.68.89.73:/opt/hibs-racing/.env ${APP}/.env" >&2
  echo "Then re-run: sudo bash ${BET}/scripts/vps_racing_repair.sh" >&2
  exit 2
fi

chown -R www-data:www-data "${APP}/data" "${LOG_DIR}" "${APP}/.env" 2>/dev/null || true
grep -q '^HIBS_URL_PREFIX=' "${APP}/.env" 2>/dev/null || echo 'HIBS_URL_PREFIX=/racing' >>"${APP}/.env"
grep -q '^HIBS_DISABLE_UI_REFRESH=' "${APP}/.env" 2>/dev/null || echo 'HIBS_DISABLE_UI_REFRESH=1' >>"${APP}/.env"

ping_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 8 http://127.0.0.1:5003/api/ping 2>/dev/null || echo 000)"
if [[ "${ping_code}" != "200" ]]; then
  log "service not healthy (ping=${ping_code}) — hard recovery"
  bash "${BET}/scripts/vps_racing_hard_recovery.sh" || warn "hard recovery failed"
fi

log "install racing crons"
if [[ -f "${BET}/deploy/cron-hibs-racing-daily.sh" ]]; then
  bash "${BET}/deploy/cron-hibs-racing-daily.sh" --install
fi
if [[ -f "${BET}/deploy/cron-hibs-racing-watchdog.sh" ]]; then
  bash "${BET}/deploy/cron-hibs-racing-watchdog.sh" --install
fi

log "daily refresh (fetch + score cards)"
if [[ -f "${BET}/deploy/cron-hibs-racing-daily.sh" ]]; then
  bash "${BET}/deploy/cron-hibs-racing-daily.sh" --run \
    >>"${LOG_DIR}/daily-refresh.log" 2>&1 || warn "daily refresh failed — see ${LOG_DIR}/daily-refresh.log"
else
  warn "missing cron-hibs-racing-daily.sh"
fi

log "diagnose (after)"
bash "${BET}/scripts/vps_racing_diagnose_cards.sh" 2>/dev/null || true

ping_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:5003/api/ping 2>/dev/null || echo 000)"
html="$(curl -sS --max-time 45 http://127.0.0.1:5003/cards 2>/dev/null || true)"
if [[ "${ping_code}" == "200" ]] && ! echo "${html}" | grep -qi 'no card in db'; then
  log "GREEN — racing service up and cards look populated"
  exit 0
fi

if [[ "${ping_code}" != "200" ]]; then
  warn "ping still not 200 — journalctl -u hibs-racing -n 50"
  exit 3
fi

warn "service up but cards empty — need Racing API keys in ${APP}/.env or Mac rsync"
echo "  tail -50 ${LOG_DIR}/daily-refresh.log"
exit 4

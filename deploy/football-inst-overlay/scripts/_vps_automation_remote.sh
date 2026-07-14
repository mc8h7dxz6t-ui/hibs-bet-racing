#!/usr/bin/env bash
# Idempotent full-stack automation — runs ON the VPS after every deploy.
# Installs all crons, repairs racing paths, ensures trading shadow soak.
#
# Invoked by scripts/_deploy_vps_post.sh (GitHub Actions / rsync deploy).
set -euo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
TRADING="${TRADING_INSTALL_ROOT:-/opt/trading-core}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"

log() { echo "[vps-automation] $*"; }
warn() { echo "[vps-automation] WARN: $*" >&2; }

[[ "$(id -u)" -eq 0 ]] || { echo "run as root" >&2; exit 1; }
cd "${APP}"

log "football env flags"
touch "${APP}/.env"
for kv in HIBS_PREDICTION_LOG_ENABLED=1 HIBS_CLV_LOG_ENABLED=1; do
  k="${kv%%=*}"
  grep -q "^${k}=" "${APP}/.env" 2>/dev/null || echo "${kv}" >>"${APP}/.env"
done
chown www-data:www-data "${APP}/.env" 2>/dev/null || true

log "install all ops crons (football + racing + cache)"
if [[ -f "${APP}/deploy/cron-hibs-ops-automation.sh" ]]; then
  bash "${APP}/deploy/cron-hibs-ops-automation.sh" --install
else
  [[ -f "${APP}/deploy/cron-hibs-calibration.sh" ]] && \
    bash "${APP}/deploy/cron-hibs-calibration.sh" --install || true
  [[ -f "${APP}/deploy/cron-hibs-racing-daily.sh" ]] && \
    bash "${APP}/deploy/cron-hibs-racing-daily.sh" --install || true
  [[ -f "${APP}/deploy/cron-hibs-racing-watchdog.sh" ]] && \
    bash "${APP}/deploy/cron-hibs-racing-watchdog.sh" --install || true
fi

if [[ -d "${RACING}" ]]; then
  log "racing production guards + raceform path"
  mkdir -p "${RACING}/data" /var/log/hibs-racing
  chown -R www-data:www-data "${RACING}/data" /var/log/hibs-racing 2>/dev/null || true
  touch "${RACING}/.env"
  grep -q '^HIBS_DISABLE_UI_REFRESH=' "${RACING}/.env" 2>/dev/null || \
    echo 'HIBS_DISABLE_UI_REFRESH=1' >>"${RACING}/.env"
  grep -q '^HIBS_URL_PREFIX=' "${RACING}/.env" 2>/dev/null || \
    echo 'HIBS_URL_PREFIX=/racing' >>"${RACING}/.env"
  if [[ -f "${APP}/scripts/lib_racing_vps_probe.sh" ]]; then
    # shellcheck source=scripts/lib_racing_vps_probe.sh
    source "${APP}/scripts/lib_racing_vps_probe.sh"
    if racing_vps_repair_raceform_env "${RACING}"; then
      log "raceform OK: $(grep RACEFORM_DB_PATH "${RACING}/.env" | tail -1)"
    else
      warn "raceform.db missing at ${RACING}/data/raceform.db — optional; upload: ./scripts/upload_raceform_to_vps.sh from Mac"
    fi
  fi
  if systemctl is-enabled hibs-racing &>/dev/null; then
    systemctl restart hibs-racing 2>/dev/null || true
  fi
else
  warn "racing root ${RACING} missing — skip racing automation"
fi

log "line shopper / FVE (local Docker on consolidated VPS)"
if [[ -f "${APP}/scripts/lib_fve_local_repair.sh" ]]; then
  bash "${APP}/scripts/lib_fve_local_repair.sh" || warn "FVE local repair skipped or failed"
elif [[ -f "${APP}/deploy/apply-vps-fve-line-trader.sh" ]]; then
  bash "${APP}/deploy/apply-vps-fve-line-trader.sh" || warn "FVE line-trader apply failed"
fi

log "trading shadow soak"
if systemctl is-active --quiet trading-shadow-soak 2>/dev/null; then
  log "trading-shadow-soak already active"
elif [[ -f "${TRADING}/deploy/install-harvested-execution-shadow.sh" ]]; then
  systemctl stop trading-paper 2>/dev/null || true
  cd "${TRADING}"
  TRADING_INSTALL_ROOT="${TRADING}" bash deploy/install-harvested-execution-shadow.sh --install-root "${TRADING}" \
    || warn "shadow soak install failed — check /etc/trading_secrets"
else
  warn "trading-core not at ${TRADING} — run deploy_shadow_to_vps.sh once from Mac or CI"
fi

log "football API probe"
PY="${APP}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY=python3
if HOME="${APP}" PYTHONPATH="${APP}/src" "${PY}" -c "
from hibs_predictor.health_probe import gather_health
row = next((a for a in gather_health().get('apis', []) if a.get('id') == 'api_football'), {})
print('api_football_ok:', row.get('ok'))
exit(0 if row.get('ok') else 1)
" 2>/dev/null; then
  log "API-Football key live"
else
  warn "API_SPORTS_FOOTBALL_KEY missing or rejected — add to ${APP}/.env"
fi

mkdir -p "${LOG_DIR}"
chown www-data:www-data "${LOG_DIR}" 2>/dev/null || true

log "institutional++ watchdog (repair + grade snapshot)"
if [[ -f "${APP}/scripts/institutional_vps_watchdog.sh" ]]; then
  bash "${APP}/scripts/institutional_vps_watchdog.sh" --repair || warn "institutional watchdog reported issues"
else
  warn "missing institutional_vps_watchdog.sh"
fi

log "crontab summary (www-data)"
crontab -u www-data -l 2>/dev/null | grep -E 'hibs-bet|hibs-racing|institutional' || warn "no hibs crons in www-data crontab"

if [[ -f "${APP}/scripts/verify_vps_relative_paths.sh" ]]; then
  bash "${APP}/scripts/verify_vps_relative_paths.sh" || warn "relative path verify failed — stale /root paths in .env (not missing raceform)"
fi

log "done — institutional++ engineering armed; evidence accumulates via cron"

if [[ -f "${APP}/deploy/cron-hibs-hands-off.sh" ]]; then
  log "hands-off cycle cron"
  bash "${APP}/deploy/cron-hibs-hands-off.sh" --install || true
fi
if [[ -f "${APP}/scripts/vps_sync_trading_core.sh" ]]; then
  log "sync trading-core"
  bash "${APP}/scripts/vps_sync_trading_core.sh" || warn "trading sync failed"
fi
for kv in HIBS_HEALTH_RACING_PROBE=1 HIBS_HEALTH_TRADING_DAY15=1; do
  k="${kv%%=*}"
  grep -q "^${k}=" "${APP}/.env" 2>/dev/null || echo "${kv}" >>"${APP}/.env"
done
if ! grep -q '^HIBS_EVIDENCE_DEPLOY_DATE=' "${APP}/.env" 2>/dev/null; then
  echo "HIBS_EVIDENCE_DEPLOY_DATE=$(date -u +%Y-%m-%d)" >>"${APP}/.env"
fi
chown www-data:www-data "${APP}/.env" 2>/dev/null || true

if [[ -f "${APP}/scripts/hands_off_cycle.sh" ]]; then
  log "initial hands-off cycle"
  bash "${APP}/scripts/hands_off_cycle.sh" || true
fi

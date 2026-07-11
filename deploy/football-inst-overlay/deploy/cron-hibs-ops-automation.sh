#!/usr/bin/env bash
# One-shot VPS ops automation: fetches, cache maintenance, evidence, racing.
#
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-ops-automation.sh --install
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-ops-automation.sh --print
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-ops-automation.sh --run-now
#
# Schedule (www-data crontab after --install):
#   06:05 UTC daily  — racing daily_refresh (hibs-racing)
#   */15 min         — racing ping watchdog (auto-restart if hung)
#   06:25 UTC Sun    — football cache prune + fixture bust
#   06:32 UTC Sun    — football audit with force_refresh (fresh API bundle)
#   06:35 UTC daily  — football audit (cache-friendly)
#   23:05 UTC daily  — football evening audit + pred-log-sync
#   07:00 UTC Sun    — calibration-fit
#   07:15 UTC daily  — nine-ten / forward evidence log
#   07:20 UTC daily  — calibration drift alert
#   07:45 UTC daily  — institutional++ watchdog (repair + grades)
#   07:35 + 14:35 UTC — seed forward snapshots (no dashboard login)
#   07:50 UTC daily  — F7 capture regression alert
#   */3 h @ :20     — football fixture warm (headless, outside gunicorn)
#   @reboot +90s    — football fixture warm after VPS boot
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-bet}"
RACING_ROOT="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
TRADING_ROOT="${TRADING_INSTALL_ROOT:-/opt/trading-core}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"
MAINT_LOG="${LOG_DIR}/cache-maintenance.log"
FRESH_LOG="${LOG_DIR}/daily-audit-am.log"
SEED_LOG="${LOG_DIR}/seed-forward.log"
F7_ALERT_LOG="${LOG_DIR}/f7-capture-alert.log"
MARKER="# hibs-bet: ops automation (fetch + cache)"
SEED_MARKER="# hibs-bet: seed forward evidence"

usage() {
  echo "Usage: $0 [--print|--install|--run-now]"
}

print_extra_lines() {
  cat <<EOF
${MARKER}
# Weekly fixture cache bust + stale prune (before Sunday fresh fetch)
25 6 * * 0 cd ${APP_ROOT} && HOME=${APP_ROOT} bash scripts/vps_cache_maintenance.sh --prune --bust-fixtures >> ${MAINT_LOG} 2>&1
# Sunday AM: force API bundle refresh (protects quota — once per week)
32 6 * * 0 cd ${APP_ROOT} && HOME=${APP_ROOT} HIBS_DAILY_AUDIT_FORCE_REFRESH=1 bash scripts/run_daily_audit_pipeline.sh >> ${FRESH_LOG} 2>&1
${SEED_MARKER}
# Headless forward snapshot seed (fixture window — after morning audit)
35 7,14 * * * cd ${APP_ROOT} && HOME=${APP_ROOT} bash scripts/seed_forward_evidence.sh --pipeline-only >> ${SEED_LOG} 2>&1
# F7 capture regression alert (after seed + sync)
50 7 * * * cd ${APP_ROOT} && HOME=${APP_ROOT} PYTHONPATH=src ${APP_ROOT}/.venv/bin/python3 scripts/alert_f7_capture_regression.py >> ${F7_ALERT_LOG} 2>&1
EOF
}

install_base_crons() {
  local missing=0
  _install_if_present() {
    local path="$1"
    if [[ -f "${path}" ]]; then
      bash "${path}" --install || true
    else
      echo "WARN: missing ${path}" >&2
      missing=$((missing + 1))
    fi
  }
  _install_if_present "${APP_ROOT}/deploy/cron-hibs-calibration.sh"
  _install_if_present "${APP_ROOT}/deploy/cron-hibs-nine-ten.sh"
  _install_if_present "${APP_ROOT}/deploy/cron-hibs-calibration-drift.sh"
  _install_if_present "${APP_ROOT}/deploy/cron-hibs-institutional-watchdog.sh"
  _install_if_present "${APP_ROOT}/deploy/cron-hibs-hands-off.sh"
  _install_if_present "${APP_ROOT}/deploy/cron-hibs-infra-fallback.sh"
  _install_if_present "${APP_ROOT}/deploy/cron-hibs-brier-circuit.sh"
  _install_if_present "${APP_ROOT}/deploy/cron-hibs-racing-pre-race-poll.sh"
  _install_if_present "${APP_ROOT}/deploy/cron-hibs-football-fixture-warm.sh"
  if [[ -f "${APP_ROOT}/deploy/cron-hibs-racing-daily.sh" ]]; then
    bash "${APP_ROOT}/deploy/cron-hibs-racing-daily.sh" --install || true
  fi
  if [[ -f "${APP_ROOT}/deploy/cron-hibs-racing-watchdog.sh" ]]; then
    bash "${APP_ROOT}/deploy/cron-hibs-racing-watchdog.sh" --install || true
  fi
  if [[ -f "${APP_ROOT}/deploy/cron-hibs-racing-scrape.sh" ]]; then
    bash "${APP_ROOT}/deploy/cron-hibs-racing-scrape.sh" --install || true
  fi
  if [[ -f "${APP_ROOT}/deploy/cron-hibs-inst-pp-weekly.sh" ]]; then
    bash "${APP_ROOT}/deploy/cron-hibs-inst-pp-weekly.sh" --install || true
  fi
  if [[ ! -f "${APP_ROOT}/deploy/cron-hibs-hands-off.sh" && -f "${APP_ROOT}/deploy/cron-hibs-three-stack-green.sh" ]]; then
    bash "${APP_ROOT}/deploy/cron-hibs-three-stack-green.sh" --install || true
  fi
  if [[ "${missing}" -gt 0 ]]; then
    echo "WARN: ${missing} base cron installer(s) missing — git pull hibs-bet overlay" >&2
  fi
  ensure_evidence_deploy_date
  ensure_racing_probe_env
  if [[ -f "${TRADING_ROOT}/deploy/cron-hibs-trading-shadow-paper-recon.sh" ]]; then
    TRADING_INSTALL_ROOT="${TRADING_ROOT}" \
      bash "${TRADING_ROOT}/deploy/cron-hibs-trading-shadow-paper-recon.sh" --install || true
  elif [[ -f "${APP_ROOT}/deploy/cron-hibs-trading-shadow-paper-recon.sh" ]]; then
    TRADING_INSTALL_ROOT="${TRADING_ROOT}" \
      bash "${APP_ROOT}/deploy/cron-hibs-trading-shadow-paper-recon.sh" --install || true
  fi
}

install_extra_cron() {
  mkdir -p "${LOG_DIR}"
  chown www-data:www-data "${LOG_DIR}" 2>/dev/null || true
  local existing tmp
  existing="$(crontab -u www-data -l 2>/dev/null || true)"
  existing="$(printf '%s\n' "${existing}" | \
    grep -vF "${MARKER}" | \
    grep -vF "${SEED_MARKER}" | \
    grep -vF 'vps_cache_maintenance.sh --prune' | \
    grep -vF 'HIBS_DAILY_AUDIT_FORCE_REFRESH=1 bash scripts/run_daily_audit_pipeline.sh' | \
    grep -vF 'seed_forward_evidence.sh --pipeline-only' | \
    grep -vF 'alert_f7_capture_regression.py' || true)"
  tmp="$(mktemp)"
  {
    printf '%s\n' "${existing}"
    echo ""
    print_extra_lines
  } >"${tmp}"
  crontab -u www-data "${tmp}"
  rm -f "${tmp}"
  echo "Installed weekly cache + Sunday fresh-fetch + seed-forward + F7 alert cron (deduped)"
}

ensure_evidence_deploy_date() {
  [[ -f "${APP_ROOT}/.env" ]] || touch "${APP_ROOT}/.env"
  if ! grep -q '^HIBS_EVIDENCE_DEPLOY_DATE=' "${APP_ROOT}/.env" 2>/dev/null; then
    echo "HIBS_EVIDENCE_DEPLOY_DATE=$(date -u +%Y-%m-%d)" >>"${APP_ROOT}/.env"
    echo "Set HIBS_EVIDENCE_DEPLOY_DATE in ${APP_ROOT}/.env"
  fi
  chown www-data:www-data "${APP_ROOT}/.env" 2>/dev/null || true
}

ensure_racing_probe_env() {
  [[ -f "${APP_ROOT}/.env" ]] || return 0
  if ! grep -q '^HIBS_HEALTH_RACING_PROBE=' "${APP_ROOT}/.env" 2>/dev/null; then
    echo "HIBS_HEALTH_RACING_PROBE=1" >>"${APP_ROOT}/.env"
    echo "Enabled HIBS_HEALTH_RACING_PROBE=1 in ${APP_ROOT}/.env"
  fi
  if ! grep -q '^HIBS_HEALTH_TRADING_DAY15=' "${APP_ROOT}/.env" 2>/dev/null; then
    echo "HIBS_HEALTH_TRADING_DAY15=1" >>"${APP_ROOT}/.env"
    echo "Enabled HIBS_HEALTH_TRADING_DAY15=1 in ${APP_ROOT}/.env"
  fi
  if ! grep -q '^HIBS_RACING_EVIDENCE_LOCAL=' "${APP_ROOT}/.env" 2>/dev/null; then
    echo "HIBS_RACING_EVIDENCE_LOCAL=1" >>"${APP_ROOT}/.env"
    echo "Enabled HIBS_RACING_EVIDENCE_LOCAL=1 in ${APP_ROOT}/.env"
  fi
}

install_all() {
  if [[ -f "${APP_ROOT}/deploy/lib_cron_dedupe.sh" ]]; then
    # shellcheck source=lib_cron_dedupe.sh
    source "${APP_ROOT}/deploy/lib_cron_dedupe.sh"
    echo "==> Crontab stats (before)"
    hibs_crontab_stats www-data || true
    if ! hibs_crontab_install_guard www-data 2>/dev/null; then
      if [[ -f "${APP_ROOT}/deploy/crontab-emergency-sports-only.sh" ]]; then
        echo "WARN: www-data crontab bloated — running emergency sports-only" >&2
        bash "${APP_ROOT}/deploy/crontab-emergency-sports-only.sh" || {
          echo "ERROR: crontab emergency failed — run manually:" >&2
          echo "  sudo bash ${APP_ROOT}/deploy/crontab-emergency-sports-only.sh" >&2
          exit 1
        }
      else
        echo "ERROR: www-data crontab bloated — run:" >&2
        echo "  sudo bash ${APP_ROOT}/deploy/crontab-emergency-sports-only.sh" >&2
        exit 1
      fi
    fi
    echo "==> Purge duplicate managed crons (pre-install)"
    hibs_crontab_purge_hibs_paths www-data
    hibs_crontab_dedupe_identical www-data
  fi
  echo "==> Base crons (football audit, calibration, nine-ten, racing)"
  install_base_crons
  echo "==> Weekly cache + Sunday force_refresh"
  install_extra_cron
  echo ""
  echo "Logs:"
  echo "  ${LOG_DIR}/daily-audit-am.log"
  echo "  ${FRESH_LOG}"
  echo "  ${MAINT_LOG}"
  echo "  ${SEED_LOG}"
  echo "  ${F7_ALERT_LOG}"
  echo "  /var/log/hibs-racing/daily-refresh.log"
  echo ""
  echo "Deploy cache bust (one-shot): add HIBS_CACHE_BUST=1 to ${APP_ROOT}/.env then redeploy"
  if [[ -f "${APP_ROOT}/deploy/lib_cron_dedupe.sh" ]]; then
    echo ""
    echo "==> Post-install crontab verify"
    # shellcheck source=lib_cron_dedupe.sh
    source "${APP_ROOT}/deploy/lib_cron_dedupe.sh"
    hibs_crontab_verify_managed || echo "WARN: duplicate cron lines detected — run deploy/cron-hibs-dedupe-all.sh"
  fi
}

run_now() {
  echo "==> cache maintenance"
  cd "${APP_ROOT}"
  bash scripts/vps_cache_maintenance.sh --prune --bust-fixtures
  echo "==> daily audit (force refresh)"
  HOME="${APP_ROOT}" HIBS_DAILY_AUDIT_FORCE_REFRESH=1 bash scripts/run_daily_audit_pipeline.sh
  if [[ -d "${RACING_ROOT}" && -f "${APP_ROOT}/scripts/vps_racing_bootstrap.sh" ]]; then
    echo "==> racing bootstrap + refresh"
    bash "${APP_ROOT}/scripts/vps_racing_bootstrap.sh" --refresh
  elif [[ -d "${RACING_ROOT}" && -f "${APP_ROOT}/deploy/cron-hibs-racing-daily.sh" ]]; then
    bash "${APP_ROOT}/deploy/cron-hibs-racing-daily.sh" --run
  fi
  if [[ -f "${APP_ROOT}/scripts/seed_forward_evidence.sh" ]]; then
    echo "==> seed forward evidence"
    HOME="${APP_ROOT}" bash "${APP_ROOT}/scripts/seed_forward_evidence.sh" --pipeline-only || true
  fi
  if [[ -d "${TRADING_ROOT}" && -f "${APP_ROOT}/scripts/vps_sync_trading_core.sh" ]]; then
    echo "==> sync trading-core from hibs-bet"
    bash "${APP_ROOT}/scripts/vps_sync_trading_core.sh" || true
  fi
}

case "${1:---print}" in
  --install) install_all ;;
  --run-now) run_now ;;
  --print)
    echo "Base: deploy/cron-hibs-calibration.sh, cron-hibs-nine-ten.sh, cron-hibs-racing-daily.sh"
    print_extra_lines
    ;;
  -h|--help) usage ;;
  *) usage; exit 1 ;;
esac

#!/usr/bin/env bash
# Cross-platform prediction results collection — football FT sync, racing paper settle, trading recon.
#
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-prediction-results-all.sh --install
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-prediction-results-all.sh --run
set -euo pipefail

BET="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
TRADING="${TRADING_INSTALL_ROOT:-/opt/trading-core}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"
LOG_FILE="${LOG_DIR}/prediction-results-all.log"
MARKER="# hibs: cross-platform prediction results"
SCRIPT="${BET}/deploy/cron-hibs-prediction-results-all.sh"
PY="${BET}/.venv/bin/python3"
RACING_CLI="${RACING}/.venv/bin/hibs-racing"

usage() {
  echo "Usage: $0 [--print|--install|--run]"
}

run_all() {
  mkdir -p "${LOG_DIR}"
  {
    echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) prediction results all platforms ====="

    if [[ -x "${PY}" && -f "${BET}/.env" ]]; then
      echo "==> football pred-log-sync"
      cd "${BET}"
      HOME="${BET}" PYTHONPATH=src HIBS_DAILY_AUDIT_SKIP_BUNDLE=1 \
        "${PY}" scripts/run_daily_audit_log.py || echo "WARN: football sync failed"
    else
      echo "WARN: football venv/.env missing — skip pred-log-sync"
    fi

    if [[ -x "${RACING_CLI}" ]]; then
      echo "==> racing score + paper settle"
      cd "${RACING}"
      HOME="${RACING}" PYTHONPATH=src "${RACING_CLI}" score-card --days 2 || echo "WARN: score-card failed"
      HOME="${RACING}" PYTHONPATH=src "${RACING_CLI}" settle-paper || echo "WARN: settle-paper failed"
      HOME="${RACING}" PYTHONPATH=src "${RACING_CLI}" reconcile-paper || echo "WARN: reconcile-paper failed"
    else
      echo "WARN: racing CLI missing — skip paper results"
    fi

    if [[ -f "${TRADING}/deploy/cron-hibs-trading-shadow-paper-recon.sh" ]]; then
      echo "==> trading shadow-paper recon"
      TRADING_INSTALL_ROOT="${TRADING}" bash "${TRADING}/deploy/cron-hibs-trading-shadow-paper-recon.sh" --run || true
    elif [[ -f "${BET}/deploy/cron-hibs-trading-shadow-paper-recon.sh" ]]; then
      TRADING_INSTALL_ROOT="${TRADING}" bash "${BET}/deploy/cron-hibs-trading-shadow-paper-recon.sh" --run || true
    fi

    echo "===== done ====="
  } >>"${LOG_FILE}" 2>&1
  chown www-data:www-data "${LOG_FILE}" 2>/dev/null || true
}

install_cron() {
  mkdir -p "${LOG_DIR}"
  local existing tmp
  existing="$(crontab -u www-data -l 2>/dev/null || true)"
  existing="$(printf '%s\n' "${existing}" | grep -vF "${MARKER}" | grep -vF 'cron-hibs-prediction-results-all.sh' || true)"
  tmp="$(mktemp)"
  {
    printf '%s\n' "${existing}"
    echo ""
    echo "${MARKER}"
    echo "# Midday FT catch-up (football + racing paper)"
    echo "5 12 * * * sudo bash ${SCRIPT} --run >> ${LOG_FILE} 2>&1"
    echo "# Evening results (after last kick-offs)"
    echo "30 22 * * * sudo bash ${SCRIPT} --run >> ${LOG_FILE} 2>&1"
    echo "# Late settle (UK/Ire cards)"
    echo "45 23 * * * sudo bash ${SCRIPT} --run >> ${LOG_FILE} 2>&1"
  } >"${tmp}"
  crontab -u www-data "${tmp}"
  rm -f "${tmp}"
  echo "Installed cross-platform prediction results cron -> ${LOG_FILE}"
}

case "${1:---print}" in
  --install) install_cron ;;
  --run) run_all ;;
  --print)
    echo "${MARKER}"
    echo "5 12 * * * sudo bash ${SCRIPT} --run >> ${LOG_FILE} 2>&1"
    echo "30 22 * * * sudo bash ${SCRIPT} --run >> ${LOG_FILE} 2>&1"
    echo "45 23 * * * sudo bash ${SCRIPT} --run >> ${LOG_FILE} 2>&1"
    ;;
  -h|--help) usage ;;
  *) usage; exit 1 ;;
esac

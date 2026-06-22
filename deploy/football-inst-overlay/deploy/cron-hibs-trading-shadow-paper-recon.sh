#!/usr/bin/env bash
# Daily shadow vs paper reconciliation + fail-closed paper submit gate.
#
#   sudo bash /opt/trading-core/deploy/cron-hibs-trading-shadow-paper-recon.sh --install
#   sudo bash /opt/trading-core/deploy/cron-hibs-trading-shadow-paper-recon.sh --run
set -euo pipefail

INSTALL_ROOT="${TRADING_INSTALL_ROOT:-/opt/trading-core}"
LOG_DIR="${LOG_DIR:-/var/log/trading-core}"
LOG_FILE="${LOG_DIR}/shadow-paper-recon.log"
MARKER="# trading-core: shadow-paper reconciliation"
SCRIPT="${INSTALL_ROOT}/deploy/cron-hibs-trading-shadow-paper-recon.sh"
PY="${INSTALL_ROOT}/.venv/bin/python3"

usage() {
  echo "Usage: $0 [--print|--install|--run]"
}

run_recon() {
  mkdir -p "${LOG_DIR}"
  {
    echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) shadow-paper recon ====="
    cd "${INSTALL_ROOT}"
    PYTHONPATH="${INSTALL_ROOT}/src" "${PY}" scripts/run_shadow_paper_reconciliation.py \
      --fail-on-divergence
  } >>"${LOG_FILE}" 2>&1 || {
    echo "WARN: divergence detected — paper submits blocked (see ${LOG_FILE})" >&2
    exit 0
  }
}

install_cron() {
  mkdir -p "${LOG_DIR}"
  local existing tmp
  existing="$(crontab -u www-data -l 2>/dev/null || true)"
  existing="$(printf '%s\n' "${existing}" | grep -vF "${MARKER}" | grep -vF "${SCRIPT}" | grep -vF 'cron-hibs-trading-shadow-paper-recon.sh' || true)"
  tmp="$(mktemp)"
  {
    printf '%s\n' "${existing}"
    echo ""
    echo "${MARKER}"
    echo "15 0 * * * sudo bash ${SCRIPT} --run"
  } >"${tmp}"
  crontab -u www-data "${tmp}"
  rm -f "${tmp}"
  echo "Installed shadow-paper reconciliation (00:15 UTC daily) -> ${LOG_FILE}"
}

case "${1:---print}" in
  --install) install_cron ;;
  --run) run_recon ;;
  --print)
    echo "${MARKER}"
    echo "15 0 * * * sudo bash ${SCRIPT} --run"
    ;;
  -h|--help) usage ;;
  *) usage; exit 1 ;;
esac

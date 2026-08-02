#!/usr/bin/env bash
# Cron: weekly raceform baseline sync + optional Sporting Life probe.
#
#   sudo bash /opt/hibs-racing/deploy/cron-hibs-raceform-sync.sh --install
#   sudo bash /opt/hibs-racing/deploy/cron-hibs-raceform-sync.sh --run
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-racing}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-racing}"
LOG_FILE="${LOG_DIR}/raceform-sync.log"
MARKER="# hibs-racing: raceform baseline sync"
SCRIPT="${APP_ROOT}/scripts/sync_raceform_baseline.sh"

usage() {
  echo "Usage: $0 [--print|--install|--run]"
}

run_cycle() {
  mkdir -p "${LOG_DIR}"
  if [[ -x "${SCRIPT}" ]]; then
    bash "${SCRIPT}" >>"${LOG_FILE}" 2>&1 || true
  fi
  if [[ -f "${APP_ROOT}/.venv/bin/python3" ]]; then
  HOME="${APP_ROOT}" PYTHONPATH="${APP_ROOT}/src" \
    "${APP_ROOT}/.venv/bin/python3" -c "
from hibs_racing.scrapers.sportinglife_client import probe_availability
import json
print(json.dumps({'sportinglife_probe': probe_availability()}))
" >>"${LOG_FILE}" 2>&1 || true
  fi
}

install_cron() {
  mkdir -p "${LOG_DIR}"
  chmod +x "${SCRIPT}" 2>/dev/null || true
  if [[ "${HIBS_OPS_MASTER_INSTALL:-0}" != "1" && -f "${APP_ROOT}/scripts/vps_racing_ops_hardening_gate.sh" ]]; then
    echo "Running racing ops hardening gate (100% required)..."
    bash "${APP_ROOT}/scripts/vps_racing_ops_hardening_gate.sh" || {
      echo "HARDENING BLOCKED — fix gate failures before --install" >&2
      exit 1
    }
  fi
  local existing tmp
  existing="$(crontab -u www-data -l 2>/dev/null || true)"
  existing="$(printf '%s\n' "${existing}" | grep -vF "${MARKER}" | grep -vF 'sync_raceform_baseline' || true)"
  tmp="$(mktemp)"
  {
    printf '%s\n' "${existing}"
    echo ""
    echo "${MARKER}"
    echo "# Sunday 04:00 UTC — raceform tag/outcomes refresh"
    echo "0 4 * * 0 cd ${APP_ROOT} && bash ${APP_ROOT}/deploy/cron-hibs-raceform-sync.sh --run"
    echo "# Daily lightweight probe (no ingest unless DB present)"
    echo "20 5 * * * cd ${APP_ROOT} && bash ${APP_ROOT}/deploy/cron-hibs-raceform-sync.sh --run"
  } >"${tmp}"
  crontab -u www-data "${tmp}"
  rm -f "${tmp}"
  echo "Installed raceform sync cron -> ${LOG_FILE}"
}

case "${1:---print}" in
  --install) install_cron ;;
  --run) run_cycle ;;
  --print)
    echo "${MARKER}"
    echo "0 4 * * 0 — weekly raceform sync"
    echo "20 5 * * * — daily probe + sync when DB present"
    ;;
  -h|--help) usage ;;
  *) usage; exit 1 ;;
esac

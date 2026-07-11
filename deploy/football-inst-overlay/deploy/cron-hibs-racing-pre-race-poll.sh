#!/usr/bin/env bash
# Pre-race Matchbook poll — steam/drift detection in 20m window (08:00–20:00 UTC).
#
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-racing-pre-race-poll.sh --install
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-racing-pre-race-poll.sh --run
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-racing}"
LOG_FILE="${LOG_DIR}/pre-race-poll.log"
MARKER="# hibs-racing: pre-race poll (2m)"
PY="${RACING}/.venv/bin/python3"

usage() { echo "Usage: $0 [--print|--install|--run]"; }

run_poll() {
  [[ -x "${PY}" ]] || PY="${RACING}/.venv/bin/python3"
  [[ -x "${PY}" ]] || { echo "missing racing venv" >&2; exit 1; }
  hour="$(date -u +%H)"
  if [[ "${hour}" -lt 8 || "${hour}" -gt 20 ]]; then
    echo "outside pre-race window (08–20 UTC)" >>"${LOG_FILE}"
    exit 0
  fi
  mkdir -p "${LOG_DIR}"
  {
    echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) pre-race poll ====="
    cd "${RACING}"
    sudo -u www-data env HOME="${RACING}" PYTHONPATH="${RACING}/src" \
      "${PY}" -m hibs_racing.cli poll-odds --once --milestone pre_race_30m
    echo "===== done ====="
  } >>"${LOG_FILE}" 2>&1
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
  existing="$(printf '%s\n' "${existing}" | grep -vF "${MARKER}" | grep -vF 'cron-hibs-racing-pre-race-poll.sh' || true)"
  tmp="$(mktemp)"
  {
    printf '%s\n' "${existing}"
    echo ""
    echo "${MARKER}"
    echo "*/2 8-20 * * * bash ${APP_ROOT}/deploy/cron-hibs-racing-pre-race-poll.sh --run >> ${LOG_FILE} 2>&1"
  } >"${tmp}"
  crontab -u www-data "${tmp}"
  rm -f "${tmp}"
  echo "Installed pre-race poll cron (every 2m, 08–20 UTC)"
}

case "${1:-}" in
  --print) crontab -u www-data -l 2>/dev/null | grep -F "${MARKER}" -A1 || true ;;
  --install) install_cron ;;
  --run) run_poll ;;
  *) usage; exit 1 ;;
esac

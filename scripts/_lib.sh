#!/bin/bash
# Shared helpers for hibs-racing automation scripts (macOS + Linux).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${ROOT}/logs"
mkdir -p "${LOG_DIR}"

activate_venv() {
  cd "${ROOT}"
  if [[ -n "${HIBS_RACING_SKIP_VENV:-}" ]]; then
    return 0
  fi
  if [[ ! -d .venv ]]; then
    echo "Creating .venv..."
    python3 -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -e ".[dev,ranker,web]" -q
}

load_env() {
  if [[ -f "${ROOT}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${ROOT}/.env"
    set +a
  fi
}

raceform_db() {
  local db="${RACEFORM_DB_PATH:-${HOME}/raceform.db}"
  db="${db/#\~/$HOME}"
  if [[ ! -f "${db}" ]]; then
    echo "ERROR: raceform.db not found at ${db} (set RACEFORM_DB_PATH in .env)" >&2
    return 1
  fi
  printf '%s' "${db}"
}

lookback_date() {
  local days="${1:-7}"
  if date -v-1d >/dev/null 2>&1; then
    date -v-"${days}"d +%Y-%m-%d
  else
    date -d "${days} days ago" +%Y-%m-%d
  fi
}

log_file() {
  local name="$1"
  printf '%s/%s.log' "${LOG_DIR}" "${name}"
}

run_logged() {
  local name="$1"
  shift
  local log
  log="$(log_file "${name}")"
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) ${name} ===" | tee -a "${log}"
  "$@" >>"${log}" 2>&1
  local rc=$?
  if [[ ${rc} -ne 0 ]]; then
    echo "FAILED (${rc}): ${name} — see ${log}" >&2
    tail -n 40 "${log}" >&2 || true
    return "${rc}"
  fi
  echo "OK: ${name}" | tee -a "${log}"
  return 0
}

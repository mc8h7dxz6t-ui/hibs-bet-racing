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
  # Cron may start with an arbitrary cwd — pin DB paths to repo root.
  if [[ -n "${HIBS_RACING_DB_PATH:-}" && "${HIBS_RACING_DB_PATH}" != /* ]]; then
    export HIBS_RACING_DB_PATH="${ROOT}/${HIBS_RACING_DB_PATH#./}"
  fi
  if [[ -z "${HIBS_RACING_DB_PATH:-}" ]]; then
    export HIBS_RACING_DB_PATH="${ROOT}/data/feature_store.sqlite"
  fi
  mkdir -p "$(dirname "${HIBS_RACING_DB_PATH}")"
  if [[ -n "${RACEFORM_DB_PATH:-}" && "${RACEFORM_DB_PATH}" != /* ]]; then
    export RACEFORM_DB_PATH="${ROOT}/${RACEFORM_DB_PATH#./}"
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

# Institutional++ cron hardening — raise FD ceiling, exclusive job lock (macOS-safe).
raise_fd_limit() {
  local target="${HIBS_FD_LIMIT:-4096}"
  ulimit -n "${target}" 2>/dev/null || true
}

_JOB_LOCK_DIR=""

release_job_lock() {
  if [[ -n "${_JOB_LOCK_DIR}" && -d "${_JOB_LOCK_DIR}" ]]; then
    rm -f "${_JOB_LOCK_DIR}/pid"
    rmdir "${_JOB_LOCK_DIR}" 2>/dev/null || true
    _JOB_LOCK_DIR=""
  fi
}

acquire_job_lock() {
  local name="${1:-daily_refresh}"
  local lock_root="${ROOT}/data/locks"
  mkdir -p "${lock_root}"
  _JOB_LOCK_DIR="${lock_root}/${name}"
  local err_log="${LOG_DIR}/cron-execution-errors.log"

  if command -v flock >/dev/null 2>&1; then
    local lock_file="${lock_root}/${name}.flock"
    exec 9>>"${lock_file}"
    if ! flock -n 9; then
      echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] CRITICAL: ${name} blocked — flock held." >>"${err_log}"
      return 1
    fi
    echo "$$" >"${_JOB_LOCK_DIR}.pid" 2>/dev/null || true
    trap release_job_lock EXIT INT TERM
    return 0
  fi

  if ! mkdir "${_JOB_LOCK_DIR}" 2>/dev/null; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] CRITICAL: ${name} blocked — lock ${_JOB_LOCK_DIR}." >>"${err_log}"
    return 1
  fi
  echo "$$" >"${_JOB_LOCK_DIR}/pid"
  trap release_job_lock EXIT INT TERM
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

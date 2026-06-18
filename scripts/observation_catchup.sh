#!/usr/bin/env bash
# Catch up missed observation refresh (Mac sleep / missed 06:00 cron).
# Safe: skips if today's batch already succeeded. Run from launchd hourly 6–11 local.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_lib.sh"

activate_venv
load_env

LOG="${LOG_DIR}/cron_daily.log"
STAMP_FILE="${ROOT}/logs/.observation_last_ok"
TODAY="$(date +%F)"

last_ok_day() {
  if [[ -f "${STAMP_FILE}" ]]; then
    head -1 "${STAMP_FILE}" 2>/dev/null || true
    return
  fi
  if [[ -f "${LOG}" ]]; then
    if tail -50 "${LOG}" 2>/dev/null | grep -q 'Daily refresh completed successfully'; then
      # best-effort: if log modified today
      if [[ "$(date -r "${LOG}" +%F 2>/dev/null || echo '')" == "${TODAY}" ]]; then
        echo "${TODAY}"
        return
      fi
    fi
  fi
  echo ""
}

if [[ "$(last_ok_day)" == "${TODAY}" ]]; then
  exit 0
fi

HOUR="$(date +%H)"
if [[ "${HOUR}" -lt 6 ]]; then
  exit 0
fi

echo "[catchup] $(date -u +%Y-%m-%dT%H:%M:%SZ) running missed observation refresh"
export HIBS_OBSERVATION_LANE=1
if bash "${SCRIPT_DIR}/daily_refresh.sh"; then
  echo "${TODAY}" >"${STAMP_FILE}"
  echo "[catchup] OK"
fi

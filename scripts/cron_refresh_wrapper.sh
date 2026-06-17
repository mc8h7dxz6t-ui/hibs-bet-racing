#!/usr/bin/env bash
# Institutional++ cron entry — FD ceiling + exclusive lock, then full daily_refresh.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_lib.sh"

raise_fd_limit

if ! acquire_job_lock "daily_refresh"; then
  exit 1
fi

export HIBS_CRON_WRAPPED=1
export HIBS_RACING_PRODUCTION="${HIBS_RACING_PRODUCTION:-0}"
export HIBS_OBSERVATION_LANE="${HIBS_OBSERVATION_LANE:-1}"
exec "${SCRIPT_DIR}/daily_refresh.sh" "$@"

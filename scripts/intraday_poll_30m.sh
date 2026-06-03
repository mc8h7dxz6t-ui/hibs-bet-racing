#!/bin/bash
# Race-day build-up poll (~30 minutes before off). Run every 15–30 min via systemd/cron.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_lib.sh"

activate_venv
load_env

export HIBS_POLL_MILESTONE=pre_race_30m

run_logged "intraday-poll-30m" \
  hibs-racing poll-odds --once --milestone pre_race_30m

echo "Intraday Matchbook poll completed (milestone=pre_race_30m)."

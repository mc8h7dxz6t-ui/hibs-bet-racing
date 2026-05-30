#!/bin/bash
# Daily: sync recent results, refresh 24h GB+IRE cards, score, odds, paper settle.
# Does NOT retrain the ranker (see weekly_retrain.sh).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_lib.sh"

activate_venv
load_env

LOOKBACK_DAYS="${HIBS_LOOKBACK_DAYS:-7}"
START_DATE="$(lookback_date "${LOOKBACK_DAYS}")"
RFDB="$(raceform_db)"

echo "hibs-racing daily refresh — results since ${START_DATE}"

run_logged "daily-ingest-sync" \
  hibs-racing ingest-raceform "${RFDB}" --since "${START_DATE}" --sync

run_logged "daily-refresh-cards" \
  hibs-racing refresh-cards \
    --source racing_api \
    --window 24 \
    --regions gb,ire \
    --odds-source auto \
    --paper

run_logged "daily-settle-paper" \
  hibs-racing settle-paper

echo "Daily refresh completed successfully."

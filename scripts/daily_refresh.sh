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

run_logged "daily-scrape-results" \
  hibs-racing scrape --days "${LOOKBACK_DAYS}" --region gb --ingest --from-cache || true
# Prefer --from-cache on daily cron; live scrape uses rp_scrape_day_pause_sec pacing in config.

run_logged "daily-refresh-cards" \
  hibs-racing refresh-cards \
    --source racing_api \
    --window 24 \
    --regions gb,ire \
    --workers 1 \
    --odds-source "${HIBS_ODDS_SOURCE:-matchbook}" \
    --paper || true

run_logged "daily-settle-paper" \
  hibs-racing settle-paper || true

run_logged "daily-notify" \
  hibs-racing notify-daily --top "${HIBS_DAILY_PICKS_TOP:-3}" || true

run_logged "daily-log-retention" \
  hibs-racing retain-logs || true

PRIMARY_DATE="$(date -u +%F)"
run_logged "daily-institutional-check" \
  hibs-racing institutional-check --days 14 --card-date "${PRIMARY_DATE}" --require-recon-clean

echo "Daily refresh completed successfully."
echo "Public track record: /tracker (paper bets logged: see refresh-cards --paper)"

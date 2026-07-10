#!/bin/bash
# Daily: sync recent results, refresh 24h GB+IRE cards, score, odds, paper settle.
# Does NOT retrain the ranker (see weekly_retrain.sh).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_lib.sh"

# When invoked directly (not via cron_refresh_wrapper.sh), still harden FD + lock.
if [[ -z "${HIBS_CRON_WRAPPED:-}" ]]; then
  raise_fd_limit
  if ! acquire_job_lock "daily_refresh"; then
    exit 1
  fi
fi

activate_venv
load_env
require_ranker_artifacts

for arg in "$@"; do
  if [[ "${arg}" == "--dry-run-quotes" ]]; then
    echo "Matchbook dry-run-quotes -> exchange_quotes"
    run_logged "dry-run-quotes" hibs-racing dry-run-quotes
    exit $?
  fi
done

LOOKBACK_DAYS="${HIBS_LOOKBACK_DAYS:-7}"
START_DATE="$(lookback_date "${LOOKBACK_DAYS}")"
RFDB="$(raceform_db)"

echo "hibs-racing daily refresh — results since ${START_DATE}"

run_logged "daily-ingest-sync" \
  hibs-racing ingest-raceform "${RFDB}" --since "${START_DATE}" --sync

# Recover missing OR / enrich fields on upcoming + cached RP racecards.
run_tier2_logged "daily-or-enrich-backfill" \
  hibs-racing backfill-runner-enrich

# TIER-2: scrape-from-cache may be empty on quiet days — do not abort refresh-cards.
if ! run_logged "daily-scrape-results" \
  hibs-racing scrape --days "${LOOKBACK_DAYS}" --region gb --ingest --from-cache; then
  echo "WARN: [TIER-2] daily-scrape-results failed — continuing" >&2
fi
# Prefer --from-cache on daily cron; live scrape uses rp_scrape_day_pause_sec pacing in config.

export HIBS_POLL_MILESTONE=baseline

run_logged "daily-refresh-cards" \
  hibs-racing refresh-cards \
    --source "${HIBS_RACING_CARD_SOURCE:-auto}" \
    --window 24 \
    --regions gb,ire \
    --workers 1 \
    --odds-source "${HIBS_ODDS_SOURCE:-auto}" \
    --poll-milestone baseline \
    --paper

run_tier2_logged "daily-settle-paper" \
  hibs-racing settle-paper

run_tier2_logged "daily-join-execution-slippage" \
  hibs-racing join-execution-slippage --days 14

run_tier2_logged "daily-notify" \
  hibs-racing notify-daily --top "${HIBS_DAILY_PICKS_TOP:-3}"

run_tier2_logged "daily-log-retention" \
  hibs-racing retain-logs

PRIMARY_DATE="$(date -u +%F)"
# TIER-2: backfill snapshots best-effort.
if ! hibs-racing snapshot-backfill --start "${START_DATE}" --end "${PRIMARY_DATE}" >/dev/null 2>&1; then
  echo "WARN: [TIER-2] snapshot-backfill incomplete" >&2
fi

OBS_LANE="${HIBS_OBSERVATION_LANE:-}"
if [[ -z "${OBS_LANE}" ]]; then
  if is_production_mode; then
    OBS_LANE=0
  else
    OBS_LANE=1
  fi
fi
INST_FLAGS=(--days 14 --card-date "${PRIMARY_DATE}")
if [[ "${OBS_LANE}" == "1" ]]; then
  INST_FLAGS+=(--observation-lane)
else
  INST_FLAGS+=(--require-recon-clean)
fi
if [[ "${OBS_LANE}" == "1" ]]; then
  set +e
  run_logged "daily-institutional-check" hibs-racing institutional-check "${INST_FLAGS[@]}"
  INST_RC=$?
  set -e
  if [[ ${INST_RC} -ne 0 ]]; then
    if is_production_mode; then
      echo "CRITICAL: institutional-check failed in production mode (${INST_RC})" >&2
      exit 1
    fi
    echo "WARN: institutional-check returned ${INST_RC} (observation lane — card refresh is the hard gate)" >&2
  fi
else
  run_logged "daily-institutional-check" hibs-racing institutional-check "${INST_FLAGS[@]}"
fi

echo "Daily refresh completed successfully."
echo "Public track record: /tracker (paper bets logged: see refresh-cards --paper)"
echo "Exchange quotes: exchange_quotes table (baseline milestone on morning refresh)"
# Mirror completion line for cron_daily.log audits (cron redirects full stdout here).
_CRON_LOG="${ROOT}/logs/cron_daily.log"
echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) daily_refresh complete ===" >>"${_CRON_LOG}" 2>/dev/null || true

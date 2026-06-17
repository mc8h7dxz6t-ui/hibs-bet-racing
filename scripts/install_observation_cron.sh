#!/bin/bash
# Install observation-lane cron ONLY — daily batch at 06:00, NO weekly_retrain.
# Use during Jun 4–10 (or any forward-data freeze). See docs/MASTER_OPERATIONS_SCORECARD §3.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WRAPPER="${SCRIPT_DIR}/cron_refresh_wrapper.sh"
PREFLIGHT="${SCRIPT_DIR}/preflight_observation_lane.sh"

chmod +x "${WRAPPER}" "${SCRIPT_DIR}/daily_refresh.sh" "${SCRIPT_DIR}/_lib.sh" "${PREFLIGHT}" 2>/dev/null || true

mkdir -p "${ROOT}/logs"

# 06:00 local — cron uses machine timezone; set Mac to Europe/London during observation.
DAILY_CRON="0 6 * * * HIBS_OBSERVATION_LANE=1 ${WRAPPER} >> ${ROOT}/logs/cron_daily.log 2>&1"

EXISTING="$(crontab -l 2>/dev/null || true)"
FILTERED="$(printf '%s\n' "${EXISTING}" | grep -v 'hibs-racing/scripts/daily_refresh.sh' | grep -v 'hibs-racing/scripts/cron_refresh_wrapper.sh' | grep -v 'hibs-racing/scripts/weekly_retrain.sh' | sed '/^$/d' || true)"

{
  printf '%s\n' "${FILTERED}"
  echo "# hibs-racing observation lane (daily only — no weekly retrain)"
  echo "${DAILY_CRON}"
} | crontab -

echo "Installed observation-lane cron:"
crontab -l | grep -A1 'observation lane' || true
echo ""
echo "Daily:  06:00 local — ${WRAPPER} (HIBS_OBSERVATION_LANE=1)"
echo "Logs:   ${ROOT}/logs/cron_daily.log"
echo ""
echo "Pre-flight: bash ${PREFLIGHT}"
echo "Smoke:      bash ${PREFLIGHT} --smoke"
echo ""
echo "Kill switch: crontab -l | grep -v 'hibs-racing/scripts/cron_refresh_wrapper.sh' | crontab -"

#!/bin/bash
# Install or update cron entries for hibs-racing automation (macOS/Linux).
# Idempotent: removes prior hibs-racing cron lines before appending fresh ones.
#
# During observation freeze (Jun 4–10): use scripts/install_observation_cron.sh instead —
# this script also installs weekly_retrain.sh which violates the model-freeze rule.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WRAPPER="${SCRIPT_DIR}/cron_refresh_wrapper.sh"
DAILY="${SCRIPT_DIR}/daily_refresh.sh"
WEEKLY="${SCRIPT_DIR}/weekly_retrain.sh"

chmod +x "${WRAPPER}" "${DAILY}" "${WEEKLY}" "${SCRIPT_DIR}/_lib.sh"

# 06:00 UK — cron uses machine local time; adjust TZ if server not in Europe/London.
DAILY_CRON="0 6 * * * ${WRAPPER} >> ${ROOT}/logs/cron_daily.log 2>&1"
WEEKLY_CRON="30 5 * * 0 ${WEEKLY} >> ${ROOT}/logs/cron_weekly.log 2>&1"

mkdir -p "${ROOT}/logs"

EXISTING="$(crontab -l 2>/dev/null || true)"
FILTERED="$(printf '%s\n' "${EXISTING}" | grep -v 'hibs-racing/scripts/daily_refresh.sh' | grep -v 'hibs-racing/scripts/cron_refresh_wrapper.sh' | grep -v 'hibs-racing/scripts/weekly_retrain.sh' | sed '/^$/d' || true)"

{
  printf '%s\n' "${FILTERED}"
  echo "# hibs-racing automation"
  echo "${DAILY_CRON}"
  echo "${WEEKLY_CRON}"
} | crontab -

echo "Installed cron jobs:"
crontab -l | grep -A2 'hibs-racing automation' || true
echo ""
echo "Daily:  06:00 local — ${WRAPPER}"
echo "Weekly: Sun 05:30 local — ${WEEKLY}"
echo "Logs:   ${ROOT}/logs/"
echo ""
echo "NOTE: During observation lane freeze, use: bash scripts/install_observation_cron.sh"

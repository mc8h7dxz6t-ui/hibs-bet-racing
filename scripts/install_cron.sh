#!/bin/bash
# Install or update cron entries for hibs-racing automation (macOS/Linux).
# Idempotent: removes prior hibs-racing cron lines before appending fresh ones.
#
# During observation freeze (Jun 4–10): use scripts/install_observation_cron.sh instead —
# weekly_retrain.sh violates the model-freeze rule; intraday poll is still safe.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WRAPPER="${SCRIPT_DIR}/cron_refresh_wrapper.sh"
DAILY="${SCRIPT_DIR}/daily_refresh.sh"
WEEKLY="${SCRIPT_DIR}/weekly_retrain.sh"
INTRADAY="${SCRIPT_DIR}/intraday_poll_30m.sh"
WEEKLY_EFFICACY="${SCRIPT_DIR}/weekly_gate_efficacy.sh"

chmod +x "${WRAPPER}" "${DAILY}" "${WEEKLY}" "${INTRADAY}" "${WEEKLY_EFFICACY}" "${SCRIPT_DIR}/_lib.sh"

# 06:00 UK — cron uses machine local time; adjust TZ if server not in Europe/London.
DAILY_CRON="0 6 * * * ${WRAPPER} >> ${ROOT}/logs/cron_daily.log 2>&1"
WEEKLY_CRON="30 5 * * 0 ${WEEKLY} >> ${ROOT}/logs/cron_weekly.log 2>&1"
# Every 30m 08:00–20:00 — Matchbook steam / pre-race quotes (activates steam gate data).
INTRADAY_CRON="*/30 8-20 * * * ${INTRADAY} >> ${ROOT}/logs/cron_intraday.log 2>&1"
# Sunday 07:10 UTC — gate efficacy + slippage report for institutional review.
EFFICACY_CRON="10 7 * * 0 ${WEEKLY_EFFICACY} >> ${ROOT}/logs/cron_weekly_efficacy.log 2>&1"

mkdir -p "${ROOT}/logs" "${ROOT}/reports"

EXISTING="$(crontab -l 2>/dev/null || true)"
FILTERED="$(printf '%s\n' "${EXISTING}" | grep -v 'hibs-racing/scripts/daily_refresh.sh' | grep -v 'hibs-racing/scripts/cron_refresh_wrapper.sh' | grep -v 'hibs-racing/scripts/weekly_retrain.sh' | grep -v 'hibs-racing/scripts/intraday_poll_30m.sh' | grep -v 'hibs-racing/scripts/weekly_gate_efficacy.sh' | sed '/^$/d' || true)"

{
  printf '%s\n' "${FILTERED}"
  echo "# hibs-racing automation"
  echo "${DAILY_CRON}"
  echo "${WEEKLY_CRON}"
  echo "${INTRADAY_CRON}"
  echo "${EFFICACY_CRON}"
} | crontab -

echo "Installed cron jobs:"
crontab -l | grep -A5 'hibs-racing automation' || true
echo ""
echo "Daily:    06:00 local — ${WRAPPER}"
echo "Weekly:   Sun 05:30 local — ${WEEKLY}"
echo "Intraday: */30 08:00–20:00 — ${INTRADAY}"
echo "Efficacy: Sun 07:10 — ${WEEKLY_EFFICACY}"
echo "Logs:     ${ROOT}/logs/"
echo ""
echo "NOTE: During observation lane freeze, use: bash scripts/install_observation_cron.sh"

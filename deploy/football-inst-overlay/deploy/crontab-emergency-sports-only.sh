#!/usr/bin/env bash
# Emergency: replace bloated crontab with sports-only minimal set.
#
# Use when: "crontab is too long; maximum number of lines is 10000"
#           or www-data crontab has thousands of duplicate hibs lines.
#
#   sudo bash /opt/hibs-bet/deploy/crontab-emergency-sports-only.sh
#   sudo bash /opt/hibs-bet/deploy/crontab-emergency-sports-only.sh --dry-run
#
# Does NOT touch governors / Inst++ nine-ten / institutional watchdog.
set -euo pipefail

BET="${APP_ROOT:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"
DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

mkdir -p "${LOG_DIR}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"

backup_crontab() {
  local user="$1"
  local dest="${LOG_DIR}/crontab-${user}.bak.${TS}"
  if crontab -u "${user}" -l >/dev/null 2>&1; then
    crontab -u "${user}" -l >"${dest}" 2>/dev/null || true
    local n
    n="$(wc -l <"${dest}" | tr -d ' ')"
    echo "Backed up ${user} crontab (${n} lines) -> ${dest}"
  else
    echo "No crontab for ${user}"
  fi
}

write_www_data_sports_crontab() {
  cat <<EOF
# hibs sports-only crontab (managed by crontab-emergency-sports-only.sh ${TS})
# Football — daily audit + pred-log-sync
# hibs-bet: daily bundle
35 6 * * * cd ${BET} && HOME=${BET} DEPLOY_PATH=${BET} bash ${BET}/deploy/cron-hibs-calibration.sh --run >> ${LOG_DIR}/daily-audit-am.log 2>&1
5 23 * * * cd ${BET} && HOME=${BET} DEPLOY_PATH=${BET} bash ${BET}/deploy/cron-hibs-calibration.sh --run --pm >> ${LOG_DIR}/daily-audit-pm.log 2>&1
# hibs-bet: football fixture warm
25 6 * * * cd ${BET} && HOME=${BET} DEPLOY_PATH=${BET} bash ${BET}/scripts/warm_football_fixtures.sh >> ${LOG_DIR}/fixture-warm.log 2>&1
20 */3 * * * cd ${BET} && HOME=${BET} DEPLOY_PATH=${BET} bash ${BET}/scripts/warm_football_fixtures.sh >> ${LOG_DIR}/fixture-warm.log 2>&1
# hibs: cross-platform prediction results
5 12 * * * cd ${BET} && HOME=${BET} bash ${BET}/deploy/cron-hibs-prediction-results-all.sh --run >> ${LOG_DIR}/prediction-results-all.log 2>&1
30 22 * * * cd ${BET} && HOME=${BET} bash ${BET}/deploy/cron-hibs-prediction-results-all.sh --run >> ${LOG_DIR}/prediction-results-all.log 2>&1
45 23 * * * cd ${BET} && HOME=${BET} bash ${BET}/deploy/cron-hibs-prediction-results-all.sh --run >> ${LOG_DIR}/prediction-results-all.log 2>&1
# hibs-bet: seed forward evidence (matchdays)
35 7,14 * * * cd ${BET} && HOME=${BET} bash ${BET}/scripts/seed_forward_evidence.sh --pipeline-only >> ${LOG_DIR}/seed-forward.log 2>&1
# Weekly calibration-fit (Sun)
0 7 * * 0 cd ${BET} && HOME=${BET} PYTHONPATH=src ${BET}/.venv/bin/python -m hibs_predictor.main calibration-fit >> ${LOG_DIR}/calibration-fit.log 2>&1
# hibs-racing: daily refresh (observation lane)
5 6 * * * cd ${BET} && HOME=${RACING} HIBS_RACING_DEPLOY_PATH=${RACING} HIBS_OBSERVATION_LANE=1 HIBS_ODDS_SOURCE=auto HIBS_RACING_CARD_SOURCE=auto bash ${BET}/deploy/cron-hibs-racing-daily.sh --run >> /var/log/hibs-racing/daily-refresh.log 2>&1
# hibs-bet: infra fallback (5m probe → soft → hard → nginx)
*/5 * * * * sudo bash ${BET}/deploy/cron-hibs-infra-fallback.sh --run >> ${LOG_DIR}/infra-fallback.log 2>&1
EOF
}

write_root_minimal_crontab() {
  # Preserve non-hibs lines from root; replace hibs block only.
  local existing filtered
  existing="$(crontab -l 2>/dev/null || true)"
  filtered="$(printf '%s\n' "${existing}" | grep -v '/opt/hibs-bet' | grep -v 'hibs-bet:' | grep -v 'hands-off' | grep -v 'football-cache-warm' | sed '/^$/d' || true)"
  {
    printf '%s\n' "${filtered}"
    echo "# hibs root minimal (${TS})"
    echo "*/30 * * * * sudo HOME=${BET} DEPLOY_PATH=${BET} bash ${BET}/scripts/hands_off_cycle.sh >> ${LOG_DIR}/hands-off-cycle.log 2>&1"
    echo "*/15 * * * * bash ${BET}/deploy/cron-hibs-racing-watchdog.sh --run >> /var/log/hibs-racing/watchdog.log 2>&1"
  }
}

echo "==> crontab emergency sports-only (${TS})"
backup_crontab www-data
backup_crontab root

NEW_WWW="$(write_www_data_sports_crontab)"
NEW_WWW_LINES="$(printf '%s\n' "${NEW_WWW}" | grep -c . || true)"
echo "New www-data crontab: ${NEW_WWW_LINES} lines"

if [[ "${DRY}" -eq 1 ]]; then
  echo "--- dry-run www-data crontab ---"
  printf '%s\n' "${NEW_WWW}"
  exit 0
fi

printf '%s\n' "${NEW_WWW}" | crontab -u www-data -
write_root_minimal_crontab | crontab -

echo "Installed sports-only crontabs."
echo "Verify:"
echo "  crontab -u www-data -l | wc -l"
echo "  crontab -l | wc -l"
echo "  bash ${BET}/scripts/verify_football_evidence_gates.sh"
if [[ -x "${RACING}/scripts/verify_racing_evidence_gates.sh" ]]; then
  echo "  bash ${RACING}/scripts/verify_racing_evidence_gates.sh"
fi

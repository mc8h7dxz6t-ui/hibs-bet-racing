#!/usr/bin/env bash
# Inst++ racing scrape-first profile — API guard, auto odds, robust scrape cron.
#
#   sudo bash /opt/hibs-racing/deploy/apply-vps-racing-scrape-first-institutional.sh
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-racing}"
ENV_FILE="${APP_ROOT}/.env"
MARKER="# --- VPS racing scrape-first institutional ---"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

[[ -d "${APP_ROOT}/src" ]] || { echo "Missing ${APP_ROOT}" >&2; exit 1; }
touch "${ENV_FILE}"

if grep -qF "${MARKER}" "${ENV_FILE}" 2>/dev/null; then
  awk -v m="${MARKER}" '$0 == m {skip=1; next} skip && /^HIBS_/ {next} skip && /^RACING_/ {next} skip && /^$/ {skip=0; next} {print}' \
    "${ENV_FILE}" >"${ENV_FILE}.tmp" && mv "${ENV_FILE}.tmp" "${ENV_FILE}"
fi

cat >>"${ENV_FILE}" <<EOF

${MARKER}
HIBS_ODDS_SOURCE=auto
HIBS_RACING_SCRAPE_FIRST=0
HIBS_ALWAYS_SCRAPE=1
HIBS_RACING_ROBUST_RESCUE=1
HIBS_RACING_RESCUE_MAX=40
HIBS_RACING_TARGET_DQ_PCT=95
HIBS_RACING_THIN_RESCUE_DQ_PCT=90
HIBS_RACING_ODDS_COVERAGE_MIN_PCT=85
HIBS_RACING_API_FORBIDDEN_TTL_HOURS=6
HIBS_RACING_API_GLOBAL_TRIP_AFTER=3
HIBS_RACING_ROBUST_SCRAPE_MAX_AGE_HOURS=3
RACING_API_PLAN=free
HIBS_MATCHBOOK_POLL_OWNER=vps
HIBS_RACING_PRESERVE_BEST_DQ=1
HIBS_RACING_CACHE_DIR=${APP_ROOT}/data/.cache
LOG_DIR=/var/log/hibs-racing
EOF

chown www-data:www-data "${ENV_FILE}" 2>/dev/null || true
chmod 640 "${ENV_FILE}" 2>/dev/null || true

systemctl restart hibs-racing 2>/dev/null || true
sleep 3

echo "==> racing scrape-first institutional profile applied"
echo "Warm: HOME=${APP_ROOT} bash ${APP_ROOT}/scripts/warm_racing_scrape.sh"
echo "Check: curl -s http://127.0.0.1:5003/api/scrape/status | python3 -m json.tool"

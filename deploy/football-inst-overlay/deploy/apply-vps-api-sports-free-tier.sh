#!/usr/bin/env bash
# Hybrid profile: API-Sports free tier ON (100 req/day) + scrapers as fallback.
#
# Prerequisite — add your key to /opt/hibs-bet/.env first:
#   API_SPORTS_FOOTBALL_KEY=your_key_from_dashboard.api-football.com
#
# Then:
#   sudo bash /opt/hibs-bet/deploy/apply-vps-api-sports-free-tier.sh
#
# Replaces scrape-first institutional (API off). Keeps MAX_DATA scrapers for xG/odds
# when the 100/day quota is exhausted. Does not enable heavy per-fixture API paths.
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-bet}"
ENV_FILE="${APP_ROOT}/.env"
MARKER="# --- VPS API-Sports free tier (hybrid scrapers) ---"
SCRAPE_MARKER="# --- VPS scrape-first institutional (API off, scrapers full) ---"
LEGACY_MARKER="# --- VPS scrape-first (API-Football off) ---"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

[[ -d "${APP_ROOT}/deploy" ]] || { echo "Missing ${APP_ROOT}" >&2; exit 1; }
touch "${ENV_FILE}"

strip_block() {
  local m="$1"
  [[ -f "${ENV_FILE}" ]] || return 0
  if ! grep -qF "${m}" "${ENV_FILE}"; then
    return 0
  fi
  local tmp
  tmp="$(mktemp)"
  awk -v m="${m}" '
    $0 == m { skip=1; next }
    skip && /^HIBS_/ { next }
    skip && /^$/ { skip=0; next }
    skip && /^[^#]/ { skip=0 }
    { print }
  ' "${ENV_FILE}" >"${tmp}"
  mv "${tmp}" "${ENV_FILE}"
}

_key_ok() {
  local py="${APP_ROOT}/.venv/bin/python3"
  [[ -x "${py}" ]] || py="python3"
  HOME="${APP_ROOT}" PYTHONPATH="${APP_ROOT}/src" "${py}" -c "
from hibs_predictor.scrape_first import usable_api_sports_key
k = usable_api_sports_key()
raise SystemExit(0 if len(k) >= 16 else 1)
" 2>/dev/null
}

strip_block "${LEGACY_MARKER}"
strip_block "${SCRAPE_MARKER}"
strip_block "${MARKER}"

if ! _key_ok; then
  cat >&2 <<EOF
ERROR: API_SPORTS_FOOTBALL_KEY missing or too short in ${ENV_FILE}

1. Get key: https://dashboard.api-football.com/
2. Add to ${ENV_FILE}:
     API_SPORTS_FOOTBALL_KEY=your_key_here
3. Re-run: sudo bash $0
EOF
  exit 1
fi

# Remove standalone API-off lines outside marker blocks (leftovers).
for _var in HIBS_DISABLE_API_SPORTS HIBS_SKIP_API_SPORTS_FIXTURES HIBS_PREFER_FOOTBALL_DATA_FIXTURES; do
  if grep -qE "^${_var}=1" "${ENV_FILE}" 2>/dev/null; then
    sed -i "/^${_var}=1/d" "${ENV_FILE}"
  fi
done

cat >>"${ENV_FILE}" <<EOF

${MARKER}
# API-Sports free: 100 requests/day, 10/min (api-football.com pricing)
# ~4 calls/hour budget — scrapers cover xG, odds, injuries when quota trips
HIBS_API_SPORTS_HOURLY_LIMIT=4
HIBS_FETCH_DAYS=3
HIBS_FIXTURE_FETCH_WORKERS=1
HIBS_ENRICH_API_SEM=1
HIBS_DASHBOARD_LITE=1
HIBS_LIVE_SNAPSHOT_ON_LOAD=0
HIBS_LIVE_POLL_SEC=300
HIBS_ENABLE_LINEUP_FETCH=0
HIBS_SKIP_API_INJURIES=1
HIBS_SKIP_API_SQUAD_DEPTH=1
HIBS_SKIP_API_PLAYER_STATS=1
HIBS_FETCH_FIXTURE_STATISTICS_XG=0
HIBS_ENABLE_PLAYER_INSIGHT=0
# Scrapers stay on — hybrid when API quota exhausted
HIBS_MAX_DATA=1
HIBS_SCRAPE_XG=1
HIBS_THIN_DATA_SCRAPE=1
HIBS_FOTMOB_RECENT=1
HIBS_ENABLE_FOTMOB_XG=1
HIBS_ENABLE_STATSBOMB_LIGHT=1
HIBS_ENABLE_FPL_EPL=1
HIBS_PREFER_SCRAPED_STANDINGS=1
HIBS_ENABLE_UNDERSTAT_LIGHT=1
HIBS_SKIP_HEAVY_WHEN_API_STRONG=1
HIBS_ALWAYS_DEEP_SCRAPE=0
HIBS_DEEP_ENRICH=1
HIBS_TARGET_DQ_PCT=90
HIBS_DEEP_ENRICH_RESCUE_LOW=1
HIBS_BUNDLE_DQ_REBOOST=1
HIBS_AUDIT_SETTLE_SCRAPE_FALLBACK=1
HIBS_SETTLE_BACKUP_ESPN=1
HIBS_ENABLE_ESPN_FIXTURES=1
HIBS_ROBUST_ODDS_SCRAPE=1
HIBS_ODDS_THIN_RESCUE=1
HIBS_ODDS_RESCUE_MAX=40
HIBS_ODDS_COVERAGE_MIN_PCT=40
HIBS_CACHE_DIR=/opt/hibs-bet/.cache
HIBS_LOW_SOURCE_AUTO_ENRICH=1
HIBS_LOW_SOURCE_BACKFILL_BUNDLE=1
HIBS_LOW_SOURCE_ENRICH_MAX=25
EOF

chown www-data:www-data "${ENV_FILE}"
chmod 640 "${ENV_FILE}"

# Clear stale rate-limit trip from scrape-first era
PY="${APP_ROOT}/.venv/bin/python3"
if [[ -x "${PY}" ]]; then
  HOME="${APP_ROOT}" PYTHONPATH="${APP_ROOT}/src" "${PY}" -c \
    "from hibs_predictor.rate_limiter import RateLimiter; RateLimiter().reset_all(); print('rate_limit_state cleared')" \
    2>/dev/null || true
fi

systemctl restart hibs-bet
sleep 4
systemctl is-active hibs-bet

echo "==> API-Sports free-tier hybrid profile applied"
echo "    API on (~4 req/h budget); scrapers for xG/odds/injuries; fixture lists use API when quota allows."
echo ""
echo "Verify:"
HOME="${APP_ROOT}" PYTHONPATH="${APP_ROOT}/src" "${PY:-python3}" -c "
from hibs_predictor.scrape_first import scrape_first_status
import json
print(json.dumps(scrape_first_status(), indent=2))
" 2>/dev/null || true
echo ""
echo "  sudo bash ${APP_ROOT}/deploy/vps-warm-and-verify.sh"
echo "  curl -s http://127.0.0.1:8000/api/health | python3 -m json.tool | head -40"

#!/usr/bin/env bash
# Scrape-first + institutional data parity (API-Sports off, six-plan scrapers on).
#
# Use after vps-sync-from-github.sh or Mac rsync when API key is expired but you
# still need MAX_DATA scraper depth, deep enrich toward 90% DQ, and FT backups.
#
#   sudo bash /opt/hibs-bet/deploy/apply-vps-scrape-first-institutional.sh
#
# Replaces the lighter apply-vps-scrape-first.sh block (HIBS_MAX_DATA=0).
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-bet}"
ENV_FILE="${APP_ROOT}/.env"
MARKER="# --- VPS scrape-first institutional (API off, scrapers full) ---"
LEGACY_MARKER="# --- VPS scrape-first (API-Football off) ---"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

[[ -d "${APP_ROOT}/deploy" ]] || { echo "Missing ${APP_ROOT} — run vps-sync-from-github.sh first." >&2; exit 1; }
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

strip_block "${LEGACY_MARKER}"
strip_block "${MARKER}"

cat >>"${ENV_FILE}" <<EOF

${MARKER}
# --- API-Sports off (expired key / quota) ---
HIBS_DISABLE_API_SPORTS=1
HIBS_PREFER_FOOTBALL_DATA_FIXTURES=1
HIBS_SKIP_API_SPORTS_FIXTURES=1
HIBS_LIVE_SNAPSHOT_ON_LOAD=0
HIBS_DASHBOARD_LITE=1
HIBS_LIVE_POLL_SEC=300
HIBS_LIVE_POLL_SEC_INPLAY=300
HIBS_LIVE_CACHE_SEC=300
HIBS_ENABLE_LINEUP_FETCH=0
HIBS_SKIP_API_INJURIES=1
HIBS_SKIP_API_SQUAD_DEPTH=1
HIBS_SKIP_API_PLAYER_STATS=1
HIBS_FETCH_FIXTURE_STATISTICS_XG=0
HIBS_ENABLE_PLAYER_INSIGHT=0
HIBS_FIXTURE_FETCH_WORKERS=1
HIBS_ENRICH_API_SEM=1
HIBS_FETCH_DAYS=5
HIBS_FBREF_BLOCKED=1
# --- Scraper six + thin rescue (same data policy as safe-production, no API burn) ---
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
# Targeted second-pass enrich for today's fixtures below 90% DQ
HIBS_DEEP_ENRICH=1
HIBS_TARGET_DQ_PCT=90
HIBS_DEEP_ENRICH_RESCUE_LOW=1
HIBS_BUNDLE_DQ_REBOOST=1
# Settlement: FDO → FotMob → ESPN backup (PR #42+)
HIBS_AUDIT_SETTLE_SCRAPE_FALLBACK=1
HIBS_SETTLE_BACKUP_ESPN=1
HIBS_ENABLE_ESPN_FIXTURES=1
HIBS_SETTLE_BACKUP_SOFASCORE=0
# --- Cache + low-source automation ---
HIBS_CACHE_DIR=/opt/hibs-bet/.cache
HIBS_LOW_SOURCE_AUTO_ENRICH=1
HIBS_LOW_SOURCE_BACKFILL_BUNDLE=1
HIBS_LOW_SOURCE_ENRICH_MAX=25
# --- Robust scrape + odds rescue (Inst++ automation) ---
HIBS_ROBUST_ODDS_SCRAPE=1
HIBS_ODDS_THIN_RESCUE=1
HIBS_ODDS_RESCUE_MAX=40
HIBS_ODDS_COVERAGE_MIN_PCT=40
HIBS_SCRAPE_CIRCUIT_FAILURES=5
HIBS_SCRAPE_CIRCUIT_OPEN_SEC=300
HIBS_ROBUST_SCRAPE_MAX_AGE_HOURS=3
HIBS_FOOTBALL_DATA_AUTO_SKIP_PAID=1
HIBS_FOOTBALL_DATA_FORBIDDEN_TTL_HOURS=24
EOF

chown www-data:www-data "${ENV_FILE}"
chmod 640 "${ENV_FILE}"

systemctl restart hibs-bet
sleep 4
systemctl is-active hibs-bet

echo "==> scrape-first institutional profile applied"
echo "    API-Sports off; MAX_DATA + FotMob/StatsBomb/Understat on; deep enrich 90%."
echo ""
echo "Verify:"
echo "  sudo bash ${APP_ROOT}/deploy/vps-warm-and-verify.sh"
echo "  curl -s http://127.0.0.1:8000/api/ping | python3 -m json.tool | head -20"
echo "  cd ${APP_ROOT} && PYTHONPATH=src .venv/bin/python scripts/measure_dq_7d.py"
echo "  cd ${APP_ROOT} && PYTHONPATH=src .venv/bin/python -m hibs_predictor.main pred-log-sync --verbose"

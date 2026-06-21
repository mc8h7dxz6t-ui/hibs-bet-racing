#!/usr/bin/env bash
# Build deploy/football-inst-overlay/ from local hibs-bet inst branch.
# Committed overlay lets VPS apply football deltas when hibs-bet.git push is blocked.
#
#   bash deploy/build-football-inst-overlay.sh
#   HIBS_BET_SRC=/path/to/hibs-bet bash deploy/build-football-inst-overlay.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${HIBS_BET_SRC:-${ROOT}/hibs-bet}"
OUT="${ROOT}/deploy/football-inst-overlay"
BASE_REF="${HIBS_BET_BASE_REF:-main}"

[[ -d "${SRC}/src/hibs_predictor" ]] || {
  echo "ERROR: hibs-bet tree missing at ${SRC}" >&2
  exit 1
}

cd "${SRC}"
FILES=()
if git rev-parse --verify "${BASE_REF}" >/dev/null 2>&1; then
  mapfile -t FILES < <(git diff "${BASE_REF}"...HEAD --name-only 2>/dev/null || true)
fi
if [[ "${#FILES[@]}" -eq 0 ]]; then
  mapfile -t FILES < <(git ls-files)
fi

# Always include inst-critical paths even if not in diff
EXTRA=(
  deploy/apply-vps-scrape-first-institutional.sh
  deploy/vps-full-data-repair.sh
  deploy/vps-warm-and-verify.sh
  deploy/vps-sync-football-inst-overlay.sh
  deploy/vps-autonomous-install.sh
  deploy/cron-hibs-low-source-scrape.sh
  deploy/cron-hibs-prediction-results-all.sh
  deploy/cron-hibs-racing-scrape.sh
  scripts/warm_low_source_scrape.sh
  scripts/warm_low_source_scrape.py
  scripts/hands_off_cycle.sh
  scripts/install_all_platform_automation.sh
  scripts/install_hands_off_automation.sh
  scripts/data_producer_repair.sh
  src/hibs_predictor/scrapers/scrape_resilience.py
  src/hibs_predictor/scrapers/robust_scrape_cycle.py
  src/hibs_predictor/scrapers/robust_odds_scrape.py
  src/hibs_predictor/scrapers/low_source_api.py
  src/hibs_predictor/football_data_guard.py
)

rm -rf "${OUT}"
mkdir -p "${OUT}"

copy_one() {
  local rel="$1"
  [[ -f "${SRC}/${rel}" ]] || return 0
  mkdir -p "${OUT}/$(dirname "${rel}")"
  cp -a "${SRC}/${rel}" "${OUT}/${rel}"
}

for f in "${FILES[@]}"; do
  copy_one "${f}"
done
for f in "${EXTRA[@]}"; do
  copy_one "${f}"
done

cat >"${OUT}/OVERLAY_REVISION" <<EOF
built_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
source=${SRC}
base_ref=${BASE_REF}
head=$(git -C "${SRC}" rev-parse --short HEAD 2>/dev/null || echo unknown)
branch=$(git -C "${SRC}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)
file_count=$(find "${OUT}" -type f | wc -l | tr -d ' ')
EOF

echo "==> overlay: ${OUT} ($(find "${OUT}" -type f | wc -l | tr -d ' ') files)"
echo "    revision: $(cat "${OUT}/OVERLAY_REVISION")"

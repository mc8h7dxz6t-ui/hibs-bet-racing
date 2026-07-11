#!/usr/bin/env bash
# Prune stale football cache + optional fixture bust (Sunday ops-automation).
#
#   bash /opt/hibs-bet/scripts/vps_cache_maintenance.sh --prune
#   bash /opt/hibs-bet/scripts/vps_cache_maintenance.sh --bust-fixtures
set -euo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
CACHE="${APP}/.cache"
PRUNE=0
BUST=0

for arg in "$@"; do
  case "${arg}" in
    --prune) PRUNE=1 ;;
    --bust-fixtures) BUST=1 ;;
  esac
done

[[ "${PRUNE}" -eq 1 || "${BUST}" -eq 1 ]] || { echo "Usage: $0 [--prune] [--bust-fixtures]" >&2; exit 1; }

if [[ "${PRUNE}" -eq 1 && -d "${CACHE}" ]]; then
  find "${CACHE}" -type f -mtime +14 -delete 2>/dev/null || true
  find "${CACHE}" -type d -empty -delete 2>/dev/null || true
  echo "pruned cache older than 14d under ${CACHE}"
fi

if [[ "${BUST}" -eq 1 ]]; then
  rm -f "${CACHE}"/all_fixtures_*.json "${CACHE}"/odds_bundle_* 2>/dev/null || true
  echo "busted fixture + odds bundle cache keys"
fi

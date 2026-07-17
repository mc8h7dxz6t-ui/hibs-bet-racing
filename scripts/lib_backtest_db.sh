#!/usr/bin/env bash
# Pick a readable feature_store for gate backtests (skip broken ramdisk).
set -euo pipefail

pick_backtest_db() {
  local p
  local -a candidates=()
  if [[ "${HIBS_RACING_BACKTEST_USE_RAMDISK:-0}" == "1" && -n "${HIBS_RACING_DB_PATH:-}" ]]; then
    candidates+=("${HIBS_RACING_DB_PATH}")
  fi
  candidates+=(
    /mnt/hibs-racing-data/data/feature_store.sqlite
    /opt/hibs-racing/data/feature_store.sqlite
  )
  if [[ -n "${HIBS_RACING_DB_PATH:-}" ]]; then
    candidates+=("${HIBS_RACING_DB_PATH}")
  fi
  candidates+=(/mnt/hibs-ramdisk/feature_store.sqlite)

  for p in "${candidates[@]}"; do
    [[ -n "$p" && -f "$p" ]] || continue
    if sqlite3 "$p" "PRAGMA query_only=ON; SELECT 1;" >/dev/null 2>&1; then
      export HIBS_RACING_DB_PATH="$p"
      echo "==> Backtest DB: $p ($(du -h "$p" | awk '{print $1}'))"
      return 0
    fi
    echo "WARN: unreadable DB skipped: $p" >&2
  done
  return 1
}

if ! pick_backtest_db; then
  echo "ERROR: no readable feature_store.sqlite" >&2
  echo "Try:" >&2
  echo "  sudo bash /opt/hibs-racing/scripts/vps_repair_ramdisk_db.sh" >&2
  echo "  export HIBS_RACING_DB_PATH=/mnt/hibs-racing-data/data/feature_store.sqlite" >&2
  exit 1
fi

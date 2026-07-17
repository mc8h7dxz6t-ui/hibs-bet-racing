#!/usr/bin/env bash
# Repair ramdisk feature_store + hydrate from persist (run as root on VPS).
set -euo pipefail

RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
RAMDISK_MOUNT="${HIBS_RAMDISK_MOUNT:-/mnt/hibs-ramdisk}"
PERSIST_DB="${HIBS_RACING_PERSIST_DATA_DIR:-/mnt/hibs-racing-data/data}/feature_store.sqlite"
RAM_DB="${RAMDISK_MOUNT}/feature_store.sqlite"

log() { echo "[repair-ramdisk-db] $*"; }

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

log "1) stop hibs-racing (release WAL locks)"
systemctl stop hibs-racing 2>/dev/null || true

log "2) remount ramdisk"
bash "${RACING}/deploy/mount-hibs-ramdisk.sh" --activate

if [[ -f "${PERSIST_DB}" ]]; then
  log "3) hydrate RAM DB from persist ($(du -h "${PERSIST_DB}" | awk '{print $1}'))"
  cp -a "${PERSIST_DB}" "${RAM_DB}"
  chown www-data:www-data "${RAM_DB}"
  chmod 0640 "${RAM_DB}"
  rm -f "${RAM_DB}-wal" "${RAM_DB}-shm" 2>/dev/null || true
elif [[ -f "${RACING}/data/feature_store.sqlite" ]]; then
  log "3) hydrate RAM DB from ${RACING}/data"
  cp -a "${RACING}/data/feature_store.sqlite" "${RAM_DB}"
  chown www-data:www-data "${RAM_DB}"
fi

log "4) probe databases"
for p in "${PERSIST_DB}" "${RAM_DB}"; do
  if [[ -f "$p" ]]; then
    if sqlite3 "$p" "SELECT count(*) FROM scored_runner_snapshots;" 2>/dev/null; then
      log "   OK $p"
    else
      log "   FAIL $p"
    fi
  else
    log "   missing $p"
  fi
done

log "5) start hibs-racing"
systemctl start hibs-racing 2>/dev/null || true
sleep 2
systemctl is-active hibs-racing 2>/dev/null || log "WARN: hibs-racing not active"

log "Done. For backtests use persist (safer while service runs):"
echo "  export HIBS_RACING_DB_PATH=${PERSIST_DB}"
echo "  bash ${RACING}/scripts/vps_gate_backtests.sh 2025-11-01 2026-06-30"

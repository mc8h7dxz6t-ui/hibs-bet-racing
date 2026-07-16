#!/usr/bin/env bash
# Sync hot RAM feature_store.sqlite to persistent block volume every 15 minutes.
#
#   sudo bash deploy/cron-hibs-ramdisk-sync.sh --install
#   sudo bash deploy/cron-hibs-ramdisk-sync.sh --run
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-racing}"
SCRIPT="${APP_ROOT}/deploy/cron-hibs-ramdisk-sync.sh"
LOG_DIR="${LOG_DIR:-/var/log/hibs-racing}"
MARKER="# hibs-racing: RAM disk feature_store sync (*/15)"

RAMDISK_MOUNT="${HIBS_RAMDISK_MOUNT:-/mnt/hibs-ramdisk}"
PERSIST_DIR="${HIBS_RACING_PERSIST_DATA_DIR:-/mnt/hibs-racing-data/data}"
RAM_DB="${RAMDISK_MOUNT}/feature_store.sqlite"
PERSIST_DB="${PERSIST_DIR}/feature_store.sqlite"

run_sync() {
  if [[ ! -f "${RAM_DB}" ]]; then
    echo "skip: no RAM DB at ${RAM_DB}"
    exit 0
  fi
  mkdir -p "${PERSIST_DIR}"
  tmp="${PERSIST_DB}.tmp.$$"
  sqlite3 "${RAM_DB}" ".backup '${tmp}'"
  mv -f "${tmp}" "${PERSIST_DB}"
  chown www-data:www-data "${PERSIST_DB}" 2>/dev/null || true
  echo "synced ${RAM_DB} -> ${PERSIST_DB} ($(date -u +%Y-%m-%dT%H:%M:%SZ))"
}

install_cron() {
  mkdir -p "${LOG_DIR}"
  chown www-data:www-data "${LOG_DIR}" 2>/dev/null || true
  local existing tmp
  existing="$(crontab -u www-data -l 2>/dev/null || true)"
  existing="$(printf '%s\n' "${existing}" | grep -vF "${MARKER}" | grep -vF "${SCRIPT}" || true)"
  tmp="$(mktemp)"
  {
    printf '%s\n' "${existing}"
    printf '\n%s\n' "${MARKER}"
    echo "*/15 * * * * ${SCRIPT} --run >> ${LOG_DIR}/ramdisk-sync.log 2>&1"
  } >"${tmp}"
  crontab -u www-data "${tmp}"
  rm -f "${tmp}"
  echo "Installed 15-minute RAM disk sync cron."
}

case "${1:---run}" in
  --run) run_sync ;;
  --install) install_cron ;;
  *)
    echo "Usage: $0 [--run|--install]" >&2
    exit 1
    ;;
esac

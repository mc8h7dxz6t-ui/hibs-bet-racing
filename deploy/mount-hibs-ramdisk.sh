#!/usr/bin/env bash
# Mount 256MB tmpfs at /mnt/hibs-ramdisk and activate feature_store.sqlite in RAM.
#
#   sudo bash deploy/mount-hibs-ramdisk.sh --activate
#   sudo bash deploy/mount-hibs-ramdisk.sh --deactivate
set -euo pipefail

RAMDISK_MOUNT="${HIBS_RAMDISK_MOUNT:-/mnt/hibs-ramdisk}"
RAMDISK_SIZE="${HIBS_RAMDISK_SIZE:-256M}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
PERSIST_DIR="${HIBS_RACING_PERSIST_DATA_DIR:-/mnt/hibs-racing-data/data}"
PERSIST_DB="${PERSIST_DIR}/feature_store.sqlite"
RAM_DB="${RAMDISK_MOUNT}/feature_store.sqlite"
ENV_FILE="${RACING}/.env"

log() { echo "[hibs-ramdisk] $*"; }

_upsert_env() {
  local key="$1" val="$2"
  if [[ -f "${ENV_FILE}" ]] && grep -q "^${key}=" "${ENV_FILE}"; then
    sed -i "s|^${key}=.*|${key}=${val}|" "${ENV_FILE}"
  else
    echo "${key}=${val}" >>"${ENV_FILE}"
  fi
}

activate() {
  mkdir -p "${RAMDISK_MOUNT}" "${PERSIST_DIR}"
  if ! mountpoint -q "${RAMDISK_MOUNT}"; then
    mount -t tmpfs -o size="${RAMDISK_SIZE}",mode=0750,uid=www-data,gid=www-data tmpfs "${RAMDISK_MOUNT}"
    log "mounted tmpfs ${RAMDISK_SIZE} at ${RAMDISK_MOUNT}"
  else
    log "already mounted: ${RAMDISK_MOUNT}"
  fi

  if [[ -f "${PERSIST_DB}" && ! -f "${RAM_DB}" ]]; then
    cp -a "${PERSIST_DB}" "${RAM_DB}"
    log "hydrated RAM DB from ${PERSIST_DB}"
  elif [[ ! -f "${RAM_DB}" ]]; then
    if [[ -f "${RACING}/data/feature_store.sqlite" ]]; then
      cp -a "${RACING}/data/feature_store.sqlite" "${RAM_DB}"
      log "hydrated RAM DB from ${RACING}/data/feature_store.sqlite"
    else
      touch "${RAM_DB}"
      chown www-data:www-data "${RAM_DB}"
      log "created empty RAM DB at ${RAM_DB}"
    fi
  fi
  chown www-data:www-data "${RAM_DB}" 2>/dev/null || true
  chmod 0640 "${RAM_DB}" 2>/dev/null || true

  _upsert_env "HIBS_RACING_DB_PATH" "${RAM_DB}"
  _upsert_env "HIBS_RACING_DATA_DIR" "${RAMDISK_MOUNT}"
  chown www-data:www-data "${ENV_FILE}" 2>/dev/null || true
  log "HIBS_RACING_DB_PATH=${RAM_DB}"
}

deactivate() {
  if [[ -f "${RAM_DB}" ]]; then
    mkdir -p "${PERSIST_DIR}"
    sqlite3 "${RAM_DB}" ".backup '${PERSIST_DB}'" 2>/dev/null || cp -a "${RAM_DB}" "${PERSIST_DB}"
    chown www-data:www-data "${PERSIST_DB}" 2>/dev/null || true
    log "flushed RAM DB to ${PERSIST_DB}"
  fi
  if mountpoint -q "${RAMDISK_MOUNT}"; then
    umount "${RAMDISK_MOUNT}" || true
    log "unmounted ${RAMDISK_MOUNT}"
  fi
}

case "${1:---activate}" in
  --activate) activate ;;
  --deactivate) deactivate ;;
  *)
    echo "Usage: $0 [--activate|--deactivate]" >&2
    exit 1
    ;;
esac

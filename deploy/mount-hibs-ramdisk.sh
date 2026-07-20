#!/usr/bin/env bash
# Mount tmpfs at /mnt/hibs-ramdisk — disk-only by default for feature_store.sqlite.
#
#   sudo bash deploy/mount-hibs-ramdisk.sh --activate
#   sudo bash deploy/mount-hibs-ramdisk.sh --deactivate
set -euo pipefail

RAMDISK_MOUNT="${HIBS_RAMDISK_MOUNT:-/mnt/hibs-ramdisk}"
RAMDISK_SIZE="${HIBS_RAMDISK_SIZE:-256M}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
PERSIST_DIR="${HIBS_RACING_PERSIST_DATA_DIR:-${RACING}/data}"
PERSIST_DB="${PERSIST_DIR}/feature_store.sqlite"
RAM_DB="${RAMDISK_MOUNT}/feature_store.sqlite"
ENV_FILE="${RACING}/.env"
FALLBACK_DB="${RACING}/data/feature_store.sqlite"

log() { echo "[hibs-ramdisk] $*"; }
warn() { echo "[hibs-ramdisk] WARN: $*" >&2; }

_upsert_env() {
  local key="$1" val="$2"
  if [[ -f "${ENV_FILE}" ]] && grep -q "^${key}=" "${ENV_FILE}"; then
    sed -i "s|^${key}=.*|${key}=${val}|" "${ENV_FILE}"
  else
    echo "${key}=${val}" >>"${ENV_FILE}"
  fi
}

_use_persist_fallback() {
  local db_path="$1"
  mkdir -p "$(dirname "${db_path}")"
  rm -f "${RAM_DB}" "${RAM_DB}-wal" "${RAM_DB}-shm" "${RAM_DB}-journal" 2>/dev/null || true
  _upsert_env "HIBS_RACING_DB_PATH" "${db_path}"
  _upsert_env "HIBS_RACING_DATA_DIR" "$(dirname "${db_path}")"
  chown www-data:www-data "${ENV_FILE}" 2>/dev/null || true
  log "persist fallback HIBS_RACING_DB_PATH=${db_path}"
}

activate() {
  if [[ "${HIBS_RACING_USE_RAMDISK:-0}" != "1" ]]; then
    warn "disk-only mode (set HIBS_RACING_USE_RAMDISK=1 to attempt RAM hydrate)"
    if [[ -n "${HIBS_RACING_DB_PATH:-}" && -f "${HIBS_RACING_DB_PATH}" ]]; then
      _use_persist_fallback "${HIBS_RACING_DB_PATH}"
    elif [[ -f "${FALLBACK_DB}" ]]; then
      _use_persist_fallback "${FALLBACK_DB}"
    else
      _use_persist_fallback "${PERSIST_DB}"
    fi
    return 0
  fi

  mkdir -p "${RAMDISK_MOUNT}" "${PERSIST_DIR}"
  if ! mountpoint -q "${RAMDISK_MOUNT}"; then
    mount -t tmpfs -o size="${RAMDISK_SIZE}",mode=0750,uid=www-data,gid=www-data tmpfs "${RAMDISK_MOUNT}" || {
      warn "tmpfs mount failed — persist fallback"
      _use_persist_fallback "${FALLBACK_DB}"
      return 0
    }
    log "mounted tmpfs ${RAMDISK_SIZE} at ${RAMDISK_MOUNT}"
  else
    log "already mounted: ${RAMDISK_MOUNT}"
  fi

  if [[ -f "${FALLBACK_DB}" && ! -f "${RAM_DB}" ]]; then
    if ! cp -a "${FALLBACK_DB}" "${RAM_DB}" 2>/dev/null; then
      warn "RAM hydrate failed — persist fallback"
      _use_persist_fallback "${FALLBACK_DB}"
      return 0
    fi
    log "hydrated RAM DB from ${FALLBACK_DB}"
  elif [[ ! -f "${RAM_DB}" ]]; then
    touch "${RAM_DB}"
    chown www-data:www-data "${RAM_DB}"
    log "created empty RAM DB at ${RAM_DB}"
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
    sqlite3 "${RAM_DB}" ".backup '${PERSIST_DB}'" 2>/dev/null || cp -a "${RAM_DB}" "${PERSIST_DB}" || true
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

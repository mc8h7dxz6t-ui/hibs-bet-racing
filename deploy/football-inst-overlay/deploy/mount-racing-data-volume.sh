#!/usr/bin/env bash
# Attach provider block storage and use it for hibs-racing SQLite + parquet (main VPS).
#
# Example (after attaching 20GB volume in control panel — device name may differ):
#   lsblk
#   sudo VOLUME_DEVICE=/dev/sdb bash /opt/hibs-bet/deploy/mount-racing-data-volume.sh
#
# Sets HIBS_RACING_DATA_DIR on the volume and enables beefy SQLite pragmas.
set -euo pipefail

VOLUME_DEVICE="${VOLUME_DEVICE:-}"
MOUNT_POINT="${MOUNT_POINT:-/mnt/hibs-racing-data}"
RACING_ROOT="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
RACING_ENV="${RACING_ROOT}/.env"
MARKER="# --- hibs-racing data volume (block storage) ---"

log() { echo "[racing-volume] $*"; }

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root" >&2
  exit 1
fi

if [[ -z "${VOLUME_DEVICE}" ]]; then
  echo "Set VOLUME_DEVICE (e.g. /dev/sdb). Run lsblk after attaching volume." >&2
  exit 1
fi

if [[ ! -b "${VOLUME_DEVICE}" ]]; then
  echo "Not a block device: ${VOLUME_DEVICE}" >&2
  exit 1
fi

log "device ${VOLUME_DEVICE} → ${MOUNT_POINT}"
mkdir -p "${MOUNT_POINT}"

if ! blkid "${VOLUME_DEVICE}" >/dev/null 2>&1; then
  log "formatting ext4 (new volume)"
  mkfs.ext4 -F -L hibs-racing-data "${VOLUME_DEVICE}"
fi

if ! mountpoint -q "${MOUNT_POINT}"; then
  mount "${VOLUME_DEVICE}" "${MOUNT_POINT}"
fi

UUID="$(blkid -s UUID -o value "${VOLUME_DEVICE}")"
FSTAB_LINE="UUID=${UUID} ${MOUNT_POINT} ext4 defaults,nofail 0 2"
grep -qF "${MOUNT_POINT}" /etc/fstab 2>/dev/null || echo "${FSTAB_LINE}" >> /etc/fstab

mkdir -p "${MOUNT_POINT}/data" "${MOUNT_POINT}/backups"
chown -R www-data:www-data "${MOUNT_POINT}"

if [[ -d "${RACING_ROOT}/data" && ! -L "${RACING_ROOT}/data" ]]; then
  if [[ -n "$(ls -A "${RACING_ROOT}/data" 2>/dev/null)" ]]; then
    log "migrating existing ${RACING_ROOT}/data → ${MOUNT_POINT}/data"
    rsync -a "${RACING_ROOT}/data/" "${MOUNT_POINT}/data/"
    mv "${RACING_ROOT}/data" "${RACING_ROOT}/data.pre-volume.bak"
  else
    rmdir "${RACING_ROOT}/data" 2>/dev/null || mv "${RACING_ROOT}/data" "${RACING_ROOT}/data.pre-volume.bak"
  fi
fi
ln -sfn "${MOUNT_POINT}/data" "${RACING_ROOT}/data"
chown -h www-data:www-data "${RACING_ROOT}/data" 2>/dev/null || true
chown -R www-data:www-data "${MOUNT_POINT}/data"

touch "${RACING_ENV}"
if ! grep -qF "${MARKER}" "${RACING_ENV}" 2>/dev/null; then
  cat >>"${RACING_ENV}" <<EOF

${MARKER}
HIBS_RACING_DATA_DIR=${MOUNT_POINT}/data
HIBS_RACING_DB_PATH=${MOUNT_POINT}/data/feature_store.sqlite
HIBS_RACING_SQLITE_BEEFY=1
HIBS_RACING_SQLITE_CACHE_KB=65536
HIBS_RACING_SQLITE_MMAP_BYTES=268435456
EOF
else
  upsert() {
    local key="$1" val="$2"
    if grep -q "^${key}=" "${RACING_ENV}" 2>/dev/null; then
      sed -i "s|^${key}=.*|${key}=${val}|" "${RACING_ENV}"
    else
      echo "${key}=${val}" >> "${RACING_ENV}"
    fi
  }
  upsert HIBS_RACING_DATA_DIR "${MOUNT_POINT}/data"
  upsert HIBS_RACING_DB_PATH "${MOUNT_POINT}/data/feature_store.sqlite"
  upsert HIBS_RACING_SQLITE_BEEFY 1
fi

systemctl restart hibs-racing 2>/dev/null || true

log "done"
df -h "${MOUNT_POINT}"
du -sh "${MOUNT_POINT}/data"/* 2>/dev/null | head -10 || true
echo "Weekly maintenance: sudo bash /opt/hibs-bet/deploy/cron-hibs-racing-sqlite-maintenance.sh --install"

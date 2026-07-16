#!/usr/bin/env bash
# One-shot main VPS go-live: sync code, block storage, crons, FVE remote link, observe.
#
# Prereqs:
#   - Attach 20GB block volume in panel (note device with lsblk — often /dev/sdb)
#   - FVE box already bootstrapped (ops-bootstrap-fve-vps.sh on 77.68.89.75)
#
# On hibs-bet-vps (77.68.89.73):
#   lsblk
#   curl -fsSL https://raw.githubusercontent.com/mc8h7dxz6t-ui/hibs-bet/main/deploy/ops-bootstrap-main-vps.sh | sudo \
#     HIBS_SYNC_REF=main \
#     HIBS_RACING_SYNC_REF=main \
#     VOLUME_DEVICE=/dev/sdb \
#     FVE_REMOTE_HOST=77.68.89.75 \
#     HIBS_PUBLIC_HOST=hibs-bet.co.uk \
#     bash
#
# Or from synced tree:
#   sudo HIBS_SYNC_REF=main VOLUME_DEVICE=/dev/sdb FVE_REMOTE_HOST=77.68.89.75 \
#     bash /opt/hibs-bet/deploy/ops-bootstrap-main-vps.sh
set -euo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
REF="${HIBS_SYNC_REF:-main}"
RACING_REF="${HIBS_RACING_SYNC_REF:-main}"
VOLUME="${VOLUME_DEVICE:-}"
FVE_HOST="${FVE_REMOTE_HOST:-77.68.89.75}"
PUBLIC="${HIBS_PUBLIC_HOST:-hibs-bet.co.uk}"

log() { echo "[ops-main] $*"; }

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root" >&2
  exit 1
fi

log "1/10 — sync hibs-bet ref=${REF}"
if [[ -f "${APP}/deploy/vps-sync-from-github.sh" ]]; then
  HIBS_SYNC_REF="${REF}" APP_ROOT="${APP}" bash "${APP}/deploy/vps-sync-from-github.sh"
else
  log "WARN: no local sync script — fetching bootstrap first"
  mkdir -p "${APP}"
  curl -fsSL "https://raw.githubusercontent.com/mc8h7dxz6t-ui/hibs-bet/${REF}/deploy/vps-sync-from-github.sh" \
    -o /tmp/vps-sync-from-github.sh
  HIBS_SYNC_REF="${REF}" APP_ROOT="${APP}" bash /tmp/vps-sync-from-github.sh
fi

log "2/10 — sync hibs-racing ref=${RACING_REF}"
if ! HIBS_RACING_SYNC_REF="${RACING_REF}" HIBS_RACING_DEPLOY_PATH="${RACING}" \
  bash "${APP}/deploy/vps-sync-racing-from-github.sh"; then
  log "WARN: racing GitHub sync failed — set /etc/hibs-bet/secrets/racing_github_token or run Mac deploy_racing_to_vps.sh"
fi

mkdir -p /etc/hibs-bet
cat >/etc/hibs-bet/stack.env <<EOF
FVE_REMOTE_HOST=${FVE_HOST}
HIBS_PUBLIC_HOST=${PUBLIC}
FVE_API_PORT=8010
EOF
chmod 640 /etc/hibs-bet/stack.env

if [[ -n "${VOLUME}" ]]; then
  log "3/10 — mount racing block storage ${VOLUME}"
  VOLUME_DEVICE="${VOLUME}" bash "${APP}/deploy/mount-racing-data-volume.sh"
else
  log "3/10 — skip block storage (set VOLUME_DEVICE=/dev/sdb to enable)"
fi

log "3b/10 — RAM disk + hot feature_store activation"
if [[ -f "${RACING}/deploy/mount-hibs-ramdisk.sh" ]]; then
  bash "${RACING}/deploy/mount-hibs-ramdisk.sh" --activate
  bash "${RACING}/deploy/cron-hibs-ramdisk-sync.sh" --install 2>/dev/null || true
else
  log "WARN: mount-hibs-ramdisk.sh not found — skip RAM disk"
fi

log "4/10 — scrape-first institutional profile"
bash "${APP}/deploy/apply-vps-scrape-first-institutional.sh"

log "5/10 — racing nginx + cross-links"
export DEPLOY_PATH="${APP}" HIBS_RACING_DEPLOY_PATH="${RACING}"
bash "${APP}/deploy/apply-vps-racing-link.sh"

log "6/10 — trading link (if installed)"
if [[ -d /opt/trading-core ]]; then
  export TRADING_INSTALL_ROOT=/opt/trading-core
  bash "${APP}/deploy/apply-vps-trading-link.sh" 2>/dev/null || log "WARN: trading link skipped"
else
  log "trading-core not at /opt/trading-core — skip (install later)"
fi

log "7/10 — FVE remote upstream ${FVE_HOST}"
FVE_REMOTE_HOST="${FVE_HOST}" DEPLOY_PATH="${APP}" HIBS_PUBLIC_HOST="${PUBLIC}" \
  bash "${APP}/deploy/apply-vps-fve-remote-host.sh"

log "8/10 — install ops crons (evidence, racing daily, watchdog)"
bash "${APP}/deploy/cron-hibs-ops-automation.sh" --install
bash "${APP}/deploy/cron-hibs-dedupe-all.sh" --purge-and-verify 2>/dev/null || true

log "9/10 — institutional verify"
bash "${APP}/deploy/vps-verify-institutional.sh" || log "WARN: verify had failures — check logs"

log "10/10 — stack observation"
HIBS_PUBLIC_HOST="${PUBLIC}" bash "${APP}/deploy/ops-observe-stack.sh"

log "10b/10 — idempotent stack wiring + .env dedupe"
bash "${APP}/deploy/ensure-vps-stack-wiring.sh" --repair || log "WARN: stack wiring had issues"

log "DONE — open https://${PUBLIC}/line-trader to observe FVE lines"
log "Evidence builds over days via crons — watch /var/log/hibs-bet/"

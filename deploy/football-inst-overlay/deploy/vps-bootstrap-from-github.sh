#!/usr/bin/env bash
# One-liner bootstrap for MAIN VPS (.52) — public GitHub, no local scripts required.
#
#   curl -fsSL https://raw.githubusercontent.com/mc8h7dxz6t-ui/hibs-bet-racing/main/deploy/football-inst-overlay/deploy/vps-bootstrap-from-github.sh | \
#     sudo HIBS_OVERLAY_REF=main FVE_REMOTE_HOST=77.68.89.75 bash
#
# Pin PR branch before merge:
#   ... | sudo HIBS_OVERLAY_REF=cursor/fix-login-500-b3fc bash
set -euo pipefail

REF="${HIBS_OVERLAY_REF:-main}"
REPO="${HIBS_OVERLAY_REPO:-mc8h7dxz6t-ui/hibs-bet-racing}"
BET="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
FVE="${FVE_REMOTE_HOST:-77.68.89.75}"
PUBLIC="${HIBS_PUBLIC_HOST:-hibs-bet.co.uk}"
RAW="https://raw.githubusercontent.com/${REPO}/${REF}/deploy/football-inst-overlay/deploy"

log() { echo "[bootstrap] $*"; }

[[ "$(id -u)" -eq 0 ]] || { echo "pipe to sudo bash" >&2; exit 1; }

log "repo=${REPO} ref=${REF} main=${BET}"

mkdir -p "${BET}/deploy" "${RACING}/deploy"
curl -fsSL "${RAW}/vps-sync-overlay-from-github.sh" -o "${BET}/deploy/vps-sync-overlay-from-github.sh"
chmod +x "${BET}/deploy/vps-sync-overlay-from-github.sh"

HIBS_OVERLAY_REF="${REF}" HIBS_OVERLAY_REPO="${REPO}" DEPLOY_PATH="${BET}" \
  HIBS_RACING_DEPLOY_PATH="${RACING}" bash "${BET}/deploy/vps-sync-overlay-from-github.sh"

mkdir -p /etc/hibs-bet
cat >/etc/hibs-bet/stack.env <<EOF
FVE_REMOTE_HOST=${FVE}
HIBS_PUBLIC_HOST=${PUBLIC}
HIBS_VPS_IP=87.106.100.52
EOF
chmod 640 /etc/hibs-bet/stack.env

if [[ -f "${BET}/scripts/vps_full_stack_recovery.sh" ]]; then
  log "full stack recovery"
  FVE_REMOTE_HOST="${FVE}" HIBS_PUBLIC_HOST="${PUBLIC}" \
    DEPLOY_PATH="${BET}" HIBS_RACING_DEPLOY_PATH="${RACING}" \
    bash "${BET}/scripts/vps_full_stack_recovery.sh" || log "recovery had warnings — check logs"
fi

if [[ -f "${BET}/scripts/verify_public_edge.sh" ]]; then
  bash "${BET}/scripts/verify_public_edge.sh" || true
fi

log "DONE — https://${PUBLIC}/"

#!/usr/bin/env bash
# One-shot FVE dedicated box (77.68.89.75): swap, block storage, Docker FVE stack.
#
# Prereqs:
#   - Attach 20GB block volume in panel (lsblk — often /dev/sdb)
#
# On FVE VPS:
#   lsblk
#   curl -fsSL https://raw.githubusercontent.com/mc8h7dxz6t-ui/hibs-bet/main/deploy/ops-bootstrap-fve-vps.sh | sudo \
#     VOLUME_DEVICE=/dev/sdb \
#     HIBS_MAIN_IP=77.68.89.73 \
#     HIBS_UPSTREAM_BASE_URL=https://hibs-bet.co.uk \
#     HIBS_FVE_RAW_BRANCH=main \
#     bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || echo /opt/hibs-bet/deploy)"
BOOT="${SCRIPT_DIR}/bootstrap-fve-dedicated-1gb.sh"

if [[ ! -f "${BOOT}" ]]; then
  mkdir -p /opt/hibs-bet/deploy
  curl -fsSL "https://raw.githubusercontent.com/mc8h7dxz6t-ui/hibs-bet/main/deploy/bootstrap-fve-dedicated-1gb.sh" \
    -o "${BOOT}"
  chmod +x "${BOOT}"
fi

export HIBS_FVE_RAW_BRANCH="${HIBS_FVE_RAW_BRANCH:-main}"
export HIBS_MAIN_IP="${HIBS_MAIN_IP:-77.68.89.73}"
export HIBS_UPSTREAM_BASE_URL="${HIBS_UPSTREAM_BASE_URL:-https://hibs-bet.co.uk}"
export VOLUME_DEVICE="${VOLUME_DEVICE:-}"
export FVE_API_PORT="${FVE_API_PORT:-8010}"

echo "[ops-fve] bootstrap FVE on dedicated 1GB box (branch=${HIBS_FVE_RAW_BRANCH})"
bash "${BOOT}"

echo ""
echo "[ops-fve] verify:"
FVE_PORT="${FVE_API_PORT}"
curl -fsS --max-time 15 "http://127.0.0.1:${FVE_PORT}/health" | python3 -m json.tool | head -30 || true
echo ""
echo "Next on MAIN VPS (77.68.89.73):"
echo "  sudo FVE_REMOTE_HOST=$(hostname -I | awk '{print $1}') bash /opt/hibs-bet/deploy/apply-vps-fve-remote-host.sh"
echo "  Or run full: ops-bootstrap-main-vps.sh with FVE_REMOTE_HOST set"

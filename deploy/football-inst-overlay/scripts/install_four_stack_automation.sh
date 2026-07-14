#!/usr/bin/env bash
# One-shot: arm hands-off automation for all four pill-switcher products on one VPS.
# Football · Racing · Trading · Line shopper (FVE / arb)
#
# Consolidated box (87.106.100.52 or any single host):
#   sudo HIBS_VPS_IP=87.106.100.52 bash /opt/hibs-bet/scripts/install_four_stack_automation.sh
#
# From Mac:
#   DEPLOY_HOST=87.106.100.52 ./scripts/install_four_stack_automation.sh --remote
set -euo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
TRADING="${TRADING_INSTALL_ROOT:-/opt/trading-core}"
PUBLIC="${HIBS_PUBLIC_HOST:-hibs-bet.co.uk}"
VPS_IP="${HIBS_VPS_IP:-87.106.100.52}"
REMOTE=0
SKIP_SYNC=0

for arg in "$@"; do
  case "${arg}" in
    --remote) REMOTE=1 ;;
    --skip-sync) SKIP_SYNC=1 ;;
  esac
done

if [[ "${REMOTE}" -eq 1 ]]; then
  HOST="${DEPLOY_HOST:-${VPS_IP}}"
  USER="${DEPLOY_USER:-root}"
  exec ssh -o BatchMode=yes -o ConnectTimeout=30 "${USER}@${HOST}" \
    "export DEPLOY_PATH='${APP}' HIBS_RACING_DEPLOY_PATH='${RACING}' TRADING_INSTALL_ROOT='${TRADING}' \
     HIBS_PUBLIC_HOST='${PUBLIC}' HIBS_VPS_IP='${VPS_IP}'; \
     bash '${APP}/scripts/install_four_stack_automation.sh'"
fi

step() { echo ""; echo "========== $* =========="; }

[[ "$(id -u)" -eq 0 ]] || { echo "run as root on VPS" >&2; exit 1; }
[[ -d "${APP}/deploy" ]] || { echo "missing ${APP} — sync hibs-bet first" >&2; exit 1; }

step "1) Consolidated stack.env (local FVE)"
mkdir -p /etc/hibs-bet
cat >/etc/hibs-bet/stack.env <<EOF
FVE_REMOTE_HOST=127.0.0.1
HIBS_PUBLIC_HOST=${PUBLIC}
HIBS_VPS_IP=${VPS_IP}
EOF

step "2) Sync latest code from GitHub main"
if [[ "${SKIP_SYNC}" -eq 0 ]]; then
  if [[ -f "${APP}/deploy/vps-sync-from-github.sh" ]]; then
    HIBS_SYNC_REF="${HIBS_SYNC_REF:-main}" APP_ROOT="${APP}" \
      bash "${APP}/deploy/vps-sync-from-github.sh"
  fi
  if [[ -f "${APP}/deploy/vps-sync-racing-from-github.sh" ]]; then
    HIBS_RACING_SYNC_REF="${HIBS_RACING_SYNC_REF:-main}" HIBS_RACING_DEPLOY_PATH="${RACING}" \
      bash "${APP}/deploy/vps-sync-racing-from-github.sh"
  fi
else
  echo "    skip sync (--skip-sync)"
fi

step "3) Product links (nginx racing + trading + FVE)"
export DEPLOY_PATH="${APP}" HIBS_RACING_DEPLOY_PATH="${RACING}"
bash "${APP}/deploy/apply-vps-racing-link.sh" 2>/dev/null || true
if [[ -d "${TRADING}" ]]; then
  export TRADING_INSTALL_ROOT="${TRADING}"
  bash "${APP}/deploy/apply-vps-trading-link.sh" 2>/dev/null || true
fi
if [[ -f "${APP}/deploy/apply-vps-fve-line-trader.sh" ]]; then
  HIBS_PUBLIC_HOST="${PUBLIC}" bash "${APP}/deploy/apply-vps-fve-line-trader.sh" || true
fi

step "4) Stack wiring + data producers"
bash "${APP}/deploy/ensure-vps-stack-wiring.sh" --repair || true
if [[ -f "${APP}/scripts/lib_fve_local_repair.sh" ]]; then
  bash "${APP}/scripts/lib_fve_local_repair.sh" || true
fi

step "5) Full VPS automation + trading recon"
if [[ -f "${APP}/scripts/_vps_automation_remote.sh" ]]; then
  export TRADING_INSTALL_ROOT="${TRADING}"
  bash "${APP}/scripts/_vps_automation_remote.sh" || true
fi
if [[ -f "${TRADING}/deploy/cron-hibs-trading-shadow-paper-recon.sh" ]]; then
  TRADING_INSTALL_ROOT="${TRADING}" \
    bash "${TRADING}/deploy/cron-hibs-trading-shadow-paper-recon.sh" --install || true
  TRADING_INSTALL_ROOT="${TRADING}" \
    bash "${TRADING}/deploy/cron-hibs-trading-shadow-paper-recon.sh" --run || true
elif [[ -f "${APP}/deploy/cron-hibs-trading-shadow-paper-recon.sh" ]]; then
  bash "${APP}/deploy/cron-hibs-trading-shadow-paper-recon.sh" --install || true
fi

step "6) Hands-off crons (30m repair loop)"
bash "${APP}/scripts/install_hands_off_automation.sh"

step "7) Four-stack verify"
if [[ -f "${APP}/scripts/vps_three_stack_green.sh" ]]; then
  bash "${APP}/scripts/vps_three_stack_green.sh" --repair || true
fi
if [[ -f "${APP}/scripts/install_fve_lines_stack.sh" ]]; then
  FVE_REMOTE_HOST=127.0.0.1 bash "${APP}/scripts/install_fve_lines_stack.sh" --verify || true
fi

cat <<EOF

========== FOUR-STACK AUTOMATION ARMED ==========
Pill switcher products (auto-repair every 30m via hands_off_cycle):

  Football   https://${PUBLIC}/
  Racing     https://${PUBLIC}/racing/
  Trading    https://${PUBLIC}/harvested-execution
  Lines/Arb  https://${PUBLIC}/line-trader

Logs:
  tail -f /var/log/hibs-bet/hands-off-cycle.log
  cat /var/log/hibs-bet/stack-wiring.json
  cat /var/log/hibs-bet/three-stack-status.json

Re-run anytime:
  sudo bash ${APP}/scripts/install_four_stack_automation.sh
EOF

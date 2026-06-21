#!/usr/bin/env bash
# One-shot VPS installer — full hands-off automation (run ON the VPS as root).
#
#   cd /opt/hibs-bet && git pull origin main
#   sudo bash scripts/install_hands_off_automation.sh
#
# From Mac (SSH):
#   DEPLOY_HOST=77.68.89.73 ./scripts/install_hands_off_automation.sh --remote
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="${DEPLOY_PATH:-/opt/hibs-bet}"
REMOTE=0

for arg in "$@"; do
  [[ "${arg}" == "--remote" ]] && REMOTE=1
done

if [[ "${REMOTE}" -eq 1 ]]; then
  HOST="${DEPLOY_HOST:-87.106.100.52}"
  USER="${DEPLOY_USER:-root}"
  exec ssh -o BatchMode=yes -o ConnectTimeout=30 "${USER}@${HOST}" \
    "export DEPLOY_PATH='${APP}'; bash '${APP}/scripts/install_hands_off_automation.sh'"
fi

[[ "$(id -u)" -eq 0 ]] || { echo "run as root on VPS" >&2; exit 1; }

step() { echo ""; echo "========== $* =========="; }

step "0) www-data cron sudoers"
if [[ -f "${APP}/deploy/install-hibs-cron-sudoers.sh" ]]; then
  bash "${APP}/deploy/install-hibs-cron-sudoers.sh"
fi

step "1) Env + evidence window"
touch "${APP}/.env"
for kv in \
  HIBS_PRODUCTION=1 \
  HIBS_PREDICTION_LOG_ENABLED=1 \
  HIBS_CLV_LOG_ENABLED=1 \
  HIBS_HEALTH_RACING_PROBE=1 \
  HIBS_HEALTH_TRADING_DAY15=1 \
  HIBS_AUTH_PUBLIC_HEALTH=1 \
  HIBS_F9_TRIAL_LEAGUES_ONLY=1; do
  k="${kv%%=*}"
  grep -q "^${k}=" "${APP}/.env" 2>/dev/null || echo "${kv}" >>"${APP}/.env"
done
grep -q '^HIBS_EVIDENCE_DEPLOY_DATE=' "${APP}/.env" 2>/dev/null || \
  echo "HIBS_EVIDENCE_DEPLOY_DATE=$(date -u +%Y-%m-%d)" >>"${APP}/.env"
chown www-data:www-data "${APP}/.env"

step "2) All ops crons"
bash "${APP}/deploy/cron-hibs-ops-automation.sh" --install

step "3) Hands-off cycle cron (30 min)"
bash "${APP}/deploy/cron-hibs-hands-off.sh" --install

step "3b) Low-source scrape cron (every 2h)"
if [[ -f "${APP}/deploy/cron-hibs-low-source-scrape.sh" ]]; then
  bash "${APP}/deploy/cron-hibs-low-source-scrape.sh" --install
fi

step "4) Trading-core sync + recon"
if [[ -f "${APP}/scripts/vps_sync_trading_core.sh" ]]; then
  bash "${APP}/scripts/vps_sync_trading_core.sh" || true
fi

step "5) Racing VPS cron"
if [[ -f "${APP}/scripts/install_racing_vps_cron.sh" ]]; then
  bash "${APP}/scripts/install_racing_vps_cron.sh" || true
fi

step "6) Initial hands-off cycle"
bash "${APP}/scripts/hands_off_cycle.sh"

step "7) Status"
if [[ -f "${APP}/scripts/all_evidence_status.sh" ]]; then
  bash "${APP}/scripts/all_evidence_status.sh" || true
fi

step "8) Inst++ automation verify"
if [[ -f "${APP}/scripts/verify_inst_pp_automation.sh" ]]; then
  bash "${APP}/scripts/verify_inst_pp_automation.sh" || true
fi

cat <<EOF

========== HANDS-OFF AUTOMATION ARMED ==========
No manual dashboard loads required — seed runs 07:35 + 14:35 UTC + on repair.

Logs:
  tail -f /var/log/hibs-bet/hands-off-cycle.log
  cat /var/log/hibs-bet/hands-off-status.json
  cat /var/log/hibs-bet/inst-pp-status.json

Verify:
  bash scripts/verify_inst_pp_automation.sh

Crons (www-data): crontab -u www-data -l | grep hibs

Evidence accumulates automatically. Trading stays shadow-only until Day-15 PASS.
EOF

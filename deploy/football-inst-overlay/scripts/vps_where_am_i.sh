#!/usr/bin/env bash
# Detect which VPS you're on and print the correct recovery commands.
#
#   bash /opt/hibs-bet/scripts/vps_where_am_i.sh
#   bash /opt/hibs-racing/deploy/football-inst-overlay/scripts/vps_where_am_i.sh
set -euo pipefail

MAIN_IP="${HIBS_MAIN_IP:-87.106.100.52}"
FVE_IP="${FVE_REMOTE_HOST:-77.68.89.75}"
LEGACY_IP="${HIBS_LEGACY_IP:-77.68.89.73}"
PUBLIC="${HIBS_PUBLIC_HOST:-hibs-bet.co.uk}"
BET="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"

ips="$(hostname -I 2>/dev/null || true)"
pub="$(curl -sS --max-time 5 ifconfig.me 2>/dev/null || true)"

role="unknown"
if [[ "${ips}" == *"${MAIN_IP}"* ]] || [[ "${pub}" == "${MAIN_IP}" ]]; then
  role="main"
elif [[ "${ips}" == *"${FVE_IP}"* ]] || [[ "${pub}" == "${FVE_IP}" ]]; then
  role="fve"
elif [[ "${ips}" == *"${LEGACY_IP}"* ]] || [[ "${pub}" == "${LEGACY_IP}" ]]; then
  role="legacy"
fi

echo "==> hibs VPS role check"
echo "    local_ips=${ips}"
echo "    public_ip=${pub:-unknown}"
echo "    role=${role}"
echo ""

case "${role}" in
  main)
    echo "MAIN (${MAIN_IP}) — football :8000, racing :5003, nginx, ${PUBLIC}"
    echo ""
    echo "1) Sync overlay (installs recovery scripts):"
    echo "   sudo bash ${RACING}/deploy/football-inst-overlay/deploy/vps-sync-football-inst-overlay.sh"
    echo "   # or if overlay only under hibs-bet:"
    echo "   sudo bash ${BET}/deploy/vps-sync-football-inst-overlay.sh"
    echo ""
    echo "2) Full recovery:"
    echo "   sudo bash ${BET}/scripts/vps_full_stack_recovery.sh"
    echo "   bash ${BET}/scripts/verify_public_edge.sh"
    echo ""
    echo "3) If scripts still missing — gold standard (existing on many .52 boxes):"
    echo "   sudo FVE_REMOTE_HOST=${FVE_IP} bash ${BET}/deploy/vps-consolidated-gold-standard.sh"
    echo ""
    echo "4) 502 nginx-only quick fix:"
    echo "   sudo bash ${BET}/scripts/vps_football_hard_recovery.sh"
    ;;
  fve)
    echo "FVE (${FVE_IP}) — lines stack :8010 only. Do NOT run football/racing recovery here."
    echo ""
    echo "   sudo HIBS_UPSTREAM_BASE_URL=https://${PUBLIC} HIBS_MAIN_IP=${MAIN_IP} \\"
    echo "     bash ${BET}/deploy/bootstrap-fve-dedicated-1gb.sh"
    echo ""
    echo "On MAIN (${MAIN_IP}) wire remote FVE:"
    echo "   sudo FVE_REMOTE_HOST=${FVE_IP} bash ${BET}/deploy/apply-vps-fve-remote-host.sh"
    ;;
  legacy)
    echo "LEGACY (${LEGACY_IP}) — retired. SSH to MAIN (${MAIN_IP}) for football/racing/nginx."
    echo "   ssh root@${MAIN_IP}"
    ;;
  *)
    echo "Could not match known hibs IPs. Expected:"
    echo "   MAIN=${MAIN_IP}  FVE=${FVE_IP}  LEGACY=${LEGACY_IP}"
    echo ""
    echo "If this is the main box, sync overlay first:"
    echo "   ls ${RACING}/deploy/football-inst-overlay/scripts/vps_full_stack_recovery.sh"
    echo "   sudo bash ${RACING}/deploy/football-inst-overlay/deploy/vps-sync-football-inst-overlay.sh"
    ;;
esac

#!/usr/bin/env bash
# Three-VPS layout for hands-off www.hibs-bet.co.uk (football + racing + trading UI + lines).
#
# | Host          | Role                                              |
# |---------------|---------------------------------------------------|
# | 87.106.100.52 | Main — nginx, football, racing, trading status    |
# | 77.68.89.75   | Lines — FVE Docker only (:8010)                   |
# | 77.68.89.73   | RETIRE — do not run trading soak (Alpaca WSS 406) |
#
# Usage:
#   # On main (.52) — all-in-one OR remote lines:
#   sudo bash /opt/hibs-bet/deploy/vps-consolidated-gold-standard.sh
#   sudo FVE_REMOTE_HOST=77.68.89.75 bash /opt/hibs-bet/deploy/vps-consolidated-gold-standard.sh
#
#   # On lines box (.75) — once:
#   sudo HIBS_UPSTREAM_BASE_URL=https://www.hibs-bet.co.uk \
#     HIBS_MAIN_IP=87.106.100.52 \
#     bash /opt/hibs-bet/deploy/bootstrap-fve-dedicated-1gb.sh
#
#   # Print-only role guide:
#   bash deploy/vps-three-host-layout.sh --print
#
#   # Run FVE bootstrap on this host (must be .75):
#   sudo HIBS_ROLE=fve bash deploy/vps-three-host-layout.sh
set -euo pipefail

MAIN_IP="${HIBS_MAIN_IP:-87.106.100.52}"
FVE_IP="${FVE_REMOTE_HOST:-77.68.89.75}"
PUBLIC="${HIBS_PUBLIC_HOST:-www.hibs-bet.co.uk}"
BET="${DEPLOY_PATH:-/opt/hibs-bet}"
ROLE="${HIBS_ROLE:-print}"

print_layout() {
  cat <<EOF
Three-VPS layout (recommended)

  MAIN  ${MAIN_IP}  — football :8000, racing :5003, nginx, trading status UI
  LINES ${FVE_IP}  — FVE scrape stack :8010 (frees RAM on main)
  LEGACY 77.68.89.73 — OFF (no soak, no cron, no rsync)

Trading shadow soak: PARKED on main (Day-15 FAIL). UI + daily recon cron only.
Do NOT move soak to .73 — duplicate Alpaca WSS → HTTP 406.

--- Main (.52) — one command ---

  sudo bash ${BET}/deploy/vps-consolidated-gold-standard.sh

With lines on .75 (preferred if FVE RAM-heavy):

  sudo FVE_REMOTE_HOST=${FVE_IP} bash ${BET}/deploy/vps-consolidated-gold-standard.sh

--- Lines box (.75) — one command ---

  sudo HIBS_UPSTREAM_BASE_URL=https://${PUBLIC} HIBS_MAIN_IP=${MAIN_IP} \\
    bash ${BET}/deploy/bootstrap-fve-dedicated-1gb.sh

  # ufw: allow ${MAIN_IP} → tcp ${FVE_API_PORT:-8010}

--- Verify (from anywhere) ---

  curl -sS --max-time 15 https://${PUBLIC}/api/ping
  curl -sS --max-time 10 https://${PUBLIC}/racing/api/ping
  curl -sS -o /dev/null -w 'harvested %{http_code}\n' --max-time 25 \\
    https://${PUBLIC}/harvested-execution
  curl -sS -o /dev/null -w 'lines %{http_code}\n' --max-time 25 \\
    https://${PUBLIC}/line-trader
  curl -sS --max-time 8 http://${FVE_IP}:8010/health

EOF
}

run_fve_bootstrap() {
  local script="${BET}/deploy/bootstrap-fve-dedicated-1gb.sh"
  [[ -f "${script}" ]] || script="$(cd "$(dirname "$0")" && pwd)/football-inst-overlay/deploy/bootstrap-fve-dedicated-1gb.sh"
  [[ -f "${script}" ]] || { echo "missing bootstrap-fve-dedicated-1gb.sh" >&2; exit 1; }
  [[ "$(id -u)" -eq 0 ]] || { echo "run as root: sudo HIBS_ROLE=fve bash $0" >&2; exit 1; }
  export HIBS_UPSTREAM_BASE_URL="${HIBS_UPSTREAM_BASE_URL:-https://${PUBLIC}}"
  export HIBS_MAIN_IP="${MAIN_IP}"
  bash "${script}"
}

case "${ROLE}" in
  print|--print)
    print_layout
    ;;
  fve)
    run_fve_bootstrap
    ;;
  main)
    [[ "$(id -u)" -eq 0 ]] || { echo "run as root" >&2; exit 1; }
    local_gs="${BET}/deploy/vps-consolidated-gold-standard.sh"
    [[ -f "${local_gs}" ]] || local_gs="$(cd "$(dirname "$0")" && pwd)/vps-consolidated-gold-standard.sh"
    FVE_REMOTE_HOST="${FVE_REMOTE_HOST:-${FVE_IP}}" bash "${local_gs}"
    ;;
  *)
    echo "Unknown HIBS_ROLE=${ROLE} (use print|main|fve)" >&2
    exit 1
    ;;
esac

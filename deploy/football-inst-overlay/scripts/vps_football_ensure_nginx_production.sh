#!/usr/bin/env bash
# Canonical production nginx for hibs-bet.co.uk — football :8000, racing :5003, FVE :8010.
#
# Fixes public 502 when localhost is OK (wrong upstream :5001 or missing site).
#
#   sudo bash /opt/hibs-bet/scripts/vps_football_ensure_nginx_production.sh
set -euo pipefail

BET="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
PUBLIC="${HIBS_PUBLIC_HOST:-hibs-bet.co.uk}"

[[ "$(id -u)" -eq 0 ]] || { echo "run as root: sudo bash $0" >&2; exit 1; }

echo "==> vps_football_ensure_nginx_production"
echo "    app=${BET} public=${PUBLIC}"

if [[ -f "${BET}/deploy/apply-vps-racing-link.sh" ]]; then
  DEPLOY_PATH="${BET}" HIBS_RACING_DEPLOY_PATH="${RACING}" HIBS_PUBLIC_HOST="${PUBLIC}" \
    bash "${BET}/deploy/apply-vps-racing-link.sh"
else
  echo "WARN: missing apply-vps-racing-link.sh" >&2
fi

if [[ -f "${BET}/scripts/lib_racing_vps_probe.sh" ]]; then
  # shellcheck source=lib_racing_vps_probe.sh
  source "${BET}/scripts/lib_racing_vps_probe.sh"
  football_vps_diagnose_502 "${BET}"
fi

local_ping="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 8 http://127.0.0.1:8000/api/ping 2>/dev/null || echo 000)"
local_root="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 12 http://127.0.0.1:8000/ 2>/dev/null || echo 000)"
pub_root="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "https://${PUBLIC}/" 2>/dev/null || echo 000)"
pub_login="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "https://${PUBLIC}/login" 2>/dev/null || echo 000)"

echo "    local ping=${local_ping} root=${local_root}"
echo "    public root=${pub_root} login=${pub_login}"

if [[ "${local_ping}" == "200" && ! "${pub_login}" =~ ^(200|302)$ ]]; then
  echo "AMBER: localhost OK, public not — re-check certbot SSL server block includes proxy_pass :8000"
  echo "    grep -n proxy_pass /etc/nginx/sites-enabled/"
fi

if [[ "${local_ping}" == "200" && "${pub_login}" =~ ^(200|302)$ ]]; then
  echo "GREEN: nginx production path OK"
  exit 0
fi

exit 1

#!/usr/bin/env bash
# Fix hibs-bet /login or / → 500 (missing login.html, auth misconfig).
#
#   sudo bash /opt/hibs-bet/scripts/vps_football_fix_login_500.sh
#   sudo bash /opt/hibs-bet/scripts/vps_football_fix_login_500.sh --disable-auth
set -euo pipefail

BET="${DEPLOY_PATH:-/opt/hibs-bet}"
DISABLE_AUTH=0
for arg in "$@"; do
  case "${arg}" in
    --disable-auth) DISABLE_AUTH=1 ;;
  esac
done

[[ "$(id -u)" -eq 0 ]] || { echo "run as root: sudo bash $0" >&2; exit 1; }
[[ -d "${BET}" ]] || { echo "missing ${BET}" >&2; exit 1; }

touch "${BET}/.env"
if [[ "${DISABLE_AUTH}" -eq 1 ]]; then
  if grep -q '^HIBS_AUTH_ENABLED=' "${BET}/.env"; then
    sed -i 's/^HIBS_AUTH_ENABLED=.*/HIBS_AUTH_ENABLED=0/' "${BET}/.env"
  else
    echo 'HIBS_AUTH_ENABLED=0' >>"${BET}/.env"
  fi
  echo "set HIBS_AUTH_ENABLED=0"
fi

LOGIN_TPL="${BET}/templates/login.html"
if [[ ! -f "${LOGIN_TPL}" ]]; then
  echo "WARN: missing ${LOGIN_TPL} — sync overlay or copy from repo deploy/football-inst-overlay/templates/login.html"
fi

# shellcheck source=lib_racing_vps_probe.sh
source "${BET}/scripts/lib_racing_vps_probe.sh"
racing_vps_patch_football_auth_dashboard "${BET}"
chown www-data:www-data "${BET}/.env" 2>/dev/null || true

echo "==> restart hibs-bet"
systemctl restart hibs-bet
sleep 3

ping_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 12 http://127.0.0.1:8000/api/ping 2>/dev/null || echo 000)"
login_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 12 http://127.0.0.1:8000/login 2>/dev/null || echo 000)"
root_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 http://127.0.0.1:8000/ 2>/dev/null || echo 000)"

echo "ping=${ping_code} login=${login_code} root=${root_code}"

if [[ "${login_code}" == "500" || "${root_code}" == "500" ]]; then
  echo ""
  echo "Still 500 — last gunicorn errors:"
  journalctl -u hibs-bet -n 25 --no-pager | tail -20 || true
  echo ""
  echo "Try: sudo bash ${BET}/scripts/vps_football_fix_login_500.sh --disable-auth"
  echo "Or:  sudo bash ${BET}/scripts/vps_football_hard_recovery.sh"
  exit 1
fi

if [[ "${ping_code}" == "200" && "${login_code}" =~ ^(200|302)$ ]]; then
  echo "GREEN: login path OK"
  exit 0
fi

echo "AMBER: partial recovery — journalctl -u hibs-bet -n 40"
exit 2

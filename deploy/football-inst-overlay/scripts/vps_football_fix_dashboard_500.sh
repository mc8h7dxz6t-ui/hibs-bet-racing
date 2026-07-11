#!/usr/bin/env bash
# Fix hibs-bet / → 500 (missing fmt_roi filter / web_format.py). No git or racing overlay required.
#
#   sudo bash /opt/hibs-bet/scripts/vps_football_fix_dashboard_500.sh
#   sudo bash /opt/hibs-bet/scripts/vps_football_fix_dashboard_500.sh --disable-auth
#
# One-shot after copying this script to the VPS (no git required):
#   sudo bash /opt/hibs-bet/scripts/vps_football_fix_dashboard_500.sh --disable-auth
set -euo pipefail

BET="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
DISABLE_AUTH=0
for arg in "$@"; do
  case "${arg}" in
    --disable-auth) DISABLE_AUTH=1 ;;
  esac
done

[[ "$(id -u)" -eq 0 ]] || { echo "run as root: sudo bash $0" >&2; exit 1; }
[[ -d "${BET}" ]] || { echo "missing ${BET}" >&2; exit 1; }

LIB="${BET}/scripts/lib_football_dashboard_fix.sh"
if [[ ! -f "${LIB}" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [[ -f "${SCRIPT_DIR}/lib_football_dashboard_fix.sh" ]]; then
    LIB="${SCRIPT_DIR}/lib_football_dashboard_fix.sh"
  else
    echo "ERROR: missing ${LIB} — copy lib_football_dashboard_fix.sh to ${BET}/scripts/" >&2
    exit 1
  fi
fi
# shellcheck source=lib_football_dashboard_fix.sh
source "${LIB}"

echo ""
echo "==> vps_football_fix_dashboard_500 (fmt_roi / web_format)"
echo "    app=${BET}"
echo ""

football_vps_apply_dashboard_fix "${BET}" "${RACING}"

touch "${BET}/.env"
if [[ "${DISABLE_AUTH}" -eq 1 ]]; then
  if grep -q '^HIBS_AUTH_ENABLED=' "${BET}/.env"; then
    sed -i 's/^HIBS_AUTH_ENABLED=.*/HIBS_AUTH_ENABLED=0/' "${BET}/.env"
  else
    echo 'HIBS_AUTH_ENABLED=0' >>"${BET}/.env"
  fi
  echo "set HIBS_AUTH_ENABLED=0"
fi
chown www-data:www-data "${BET}/.env" 2>/dev/null || true

PY="${BET}/.venv/bin/python3"
if [[ -x "${PY}" ]]; then
  echo "==> import test"
  if ! timeout 90 sudo -u www-data env \
    HOME="${BET}" DEPLOY_PATH="${BET}" PYTHONPATH="${BET}/src" \
    HIBS_CACHE_DIR="${BET}/.cache" \
    "${PY}" -c "from hibs_predictor.web import app; from hibs_predictor.web_format import fmt_roi; assert app.jinja_env.filters.get('fmt_roi') is fmt_roi; print('import ok')"; then
    echo "ERROR: import failed — journalctl -u hibs-bet -n 30" >&2
    exit 2
  fi
fi

echo "==> restart hibs-bet"
systemctl restart hibs-bet
sleep 4

ping_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 12 http://127.0.0.1:8000/api/ping 2>/dev/null || echo 000)"
login_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 12 http://127.0.0.1:8000/login 2>/dev/null || echo 000)"
root_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 http://127.0.0.1:8000/ 2>/dev/null || echo 000)"

echo "ping=${ping_code} login=${login_code} root=${root_code}"

if [[ "${root_code}" == "500" ]]; then
  echo ""
  echo "Still root=500 — last errors:"
  tail -30 "${BET}/logs/hibs-bet.log" 2>/dev/null || journalctl -u hibs-bet -n 25 --no-pager || true
  exit 1
fi

if [[ "${ping_code}" == "200" && "${root_code}" =~ ^(200|302)$ ]]; then
  echo "GREEN: dashboard OK (root=${root_code})"
  exit 0
fi

echo "AMBER: partial recovery — journalctl -u hibs-bet -n 40"
exit 2

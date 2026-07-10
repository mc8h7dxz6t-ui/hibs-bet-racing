#!/usr/bin/env bash
# Hard recovery for racing 502 / stuck :5003 (do NOT curl /cards during bring-up).
#
#   sudo bash /opt/hibs-bet/scripts/vps_racing_hard_recovery.sh
set -euo pipefail

APP="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
BET="${HIBS_BET_DEPLOY_PATH:-/opt/hibs-bet}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-racing}"

log() { echo "[racing-hard] $*"; }
warn() { echo "[racing-hard] WARN: $*" >&2; }

[[ "$(id -u)" -eq 0 ]] || { echo "run as root: sudo bash $0" >&2; exit 1; }
[[ -d "${APP}" ]] || { echo "missing ${APP}" >&2; exit 1; }

# shellcheck source=lib_racing_vps_probe.sh
source "${BET}/scripts/lib_racing_vps_probe.sh"

mkdir -p "${LOG_DIR}" "${APP}/deploy"
export HIBS_RACING_DEPLOY_PATH="${APP}"
export HIBS_BET_DEPLOY_PATH="${BET}"

echo ""
echo "==> vps_racing_hard_recovery v2 (self-contained)"
echo "    app=${APP}"
echo ""

echo "==> preflight"
free -h | head -2 | sed 's/^/    /'
if ss -ltn 2>/dev/null | grep -q ':5003 '; then
  aq="$(racing_vps_accept_queue 5003)"
  echo "    NOTE: :5003 already listening, accept_queue=${aq}"
  echo "          backlog >0 means worker is stuck (often /cards) — hard kill next"
fi

echo ""
echo "==> hard kill gunicorn + free :5003"
racing_vps_kill_stale_gunicorn 5003

echo ""
echo "==> fix systemd WSGI"
racing_vps_fix_systemd_wsgi "${APP}" "${BET}"
echo "    gunicorn app=hibs_racing.web:create_app() (gthread config: deploy/gunicorn-racing.conf.py)"

echo ""
echo "==> import test as www-data"
PY="${APP}/.venv/bin/python3"
[[ -x "${PY}" ]] || { echo "missing ${PY}" >&2; exit 1; }
echo "    import test (120s) hibs_racing.web:create_app()"
if ! timeout 120 sudo -u www-data env HOME="${APP}" PYTHONPATH="${APP}/src" "${PY}" -c \
  "from hibs_racing.web import create_app; create_app(); print('import ok')"; then
  echo "ERROR: import failed — journalctl -u hibs-racing -n 40" >&2
  exit 2
fi
echo "import ok"

racing_vps_fix_data_permissions "${APP}"

echo ""
echo "==> start + wait port + ping (do NOT curl /cards)"
systemctl reset-failed hibs-racing 2>/dev/null || true
systemctl start hibs-racing 2>/dev/null || systemctl restart hibs-racing
port_wait="$(racing_vps_wait_port 5003 90 || echo fail)"
if [[ "${port_wait}" == "fail" ]]; then
  echo "ERROR: port 5003 did not come up" >&2
  journalctl -u hibs-racing -n 30 --no-pager >&2 || true
  exit 3
fi
aq="$(racing_vps_accept_queue 5003)"
echo "    port 5003 up (${port_wait}s) accept_queue=${aq}"

ping_wait="$(racing_vps_wait_http "http://127.0.0.1:5003/api/ping" 60 || echo fail)"
if [[ "${ping_wait}" == "fail" ]]; then
  echo "ERROR: ping not 200" >&2
  exit 4
fi
echo "    ping 200 (${ping_wait}s)"

echo ""
echo "==> smoke"
ping_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:5003/api/ping 2>/dev/null || echo 000)"
port_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:5003/api/portfolio/summary 2>/dev/null || echo 000)"
echo "    ping=${ping_code} portfolio=${port_code}"

if [[ "${ping_code}" == "200" ]]; then
  echo ""
  echo "GREEN: hibs-racing service recovered (ping OK)."
  exit 0
fi

warn "recovery incomplete — journalctl -u hibs-racing -n 50"
exit 5

#!/usr/bin/env bash
# Hard recovery for football 502 / stuck :8000 (login, FVE upstream, nginx proxy).
#
#   sudo bash /opt/hibs-bet/scripts/vps_football_hard_recovery.sh
set -euo pipefail

BET="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"

log() { echo "[football-hard] $*"; }
warn() { echo "[football-hard] WARN: $*" >&2; }

[[ "$(id -u)" -eq 0 ]] || { echo "run as root: sudo bash $0" >&2; exit 1; }
[[ -d "${BET}" ]] || { echo "missing ${BET}" >&2; exit 1; }

# shellcheck source=lib_racing_vps_probe.sh
source "${BET}/scripts/lib_racing_vps_probe.sh"

mkdir -p "${LOG_DIR}" "${BET}/.cache"
export DEPLOY_PATH="${BET}"
export HIBS_RACING_DEPLOY_PATH="${RACING}"

echo ""
echo "==> vps_football_hard_recovery v1 (self-contained)"
echo "    app=${BET}"
echo ""

echo "==> preflight"
free -h | head -2 | sed 's/^/    /'
if ss -ltn 2>/dev/null | grep -q ':8000 '; then
  aq="$(racing_vps_accept_queue 8000)"
  echo "    NOTE: :8000 already listening, accept_queue=${aq}"
fi

echo ""
echo "==> env + auth guards"
touch "${BET}/.env"
grep -q '^HIBS_CACHE_DIR=' "${BET}/.env" 2>/dev/null || echo 'HIBS_CACHE_DIR=/opt/hibs-bet/.cache' >>"${BET}/.env"
grep -q '^HOME=' "${BET}/.env" 2>/dev/null || echo 'HOME=/opt/hibs-bet' >>"${BET}/.env"
racing_vps_ensure_football_secret "${BET}"
racing_vps_patch_football_auth_dashboard "${BET}"
chown www-data:www-data "${BET}/.env" 2>/dev/null || true

echo ""
echo "==> hard kill gunicorn + free :8000"
racing_vps_kill_football_gunicorn 8000

echo ""
echo "==> fix systemd unit"
racing_vps_fix_football_systemd "${BET}"

PY="${BET}/.venv/bin/python3"
[[ -x "${PY}" ]] || { echo "missing ${PY}" >&2; exit 1; }

echo ""
echo "==> import test as www-data"
echo "    import test (120s) hibs_predictor.web:app"
if ! timeout 120 sudo -u www-data env \
  HOME="${BET}" \
  DEPLOY_PATH="${BET}" \
  PYTHONPATH="${BET}/src:${RACING}/src" \
  HIBS_CACHE_DIR="${BET}/.cache" \
  "${PY}" -c "from hibs_predictor.web import app; print('import ok', app.name)"; then
  echo "ERROR: import failed — journalctl -u hibs-bet -n 40" >&2
  exit 2
fi
echo "import ok"

echo ""
echo "==> start + wait port + ping"
systemctl reset-failed hibs-bet 2>/dev/null || true
systemctl start hibs-bet 2>/dev/null || systemctl restart hibs-bet
port_wait="$(racing_vps_wait_port 8000 90 || echo fail)"
if [[ "${port_wait}" == "fail" ]]; then
  echo "ERROR: port 8000 did not come up" >&2
  journalctl -u hibs-bet -n 30 --no-pager >&2 || true
  exit 3
fi
aq="$(racing_vps_accept_queue 8000)"
echo "    port 8000 up (${port_wait}s) accept_queue=${aq}"

ping_wait="$(racing_vps_wait_http "http://127.0.0.1:8000/api/ping" 60 || echo fail)"
if [[ "${ping_wait}" == "fail" ]]; then
  echo "ERROR: /api/ping not 200" >&2
  journalctl -u hibs-bet -n 30 --no-pager >&2 || true
  exit 4
fi
echo "    ping 200 (${ping_wait}s)"

login_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 http://127.0.0.1:8000/login 2>/dev/null || echo 000)"
echo "    login ${login_code}"

echo ""
echo "==> smoke"
ping_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:8000/api/ping 2>/dev/null || echo 000)"
echo "    ping=${ping_code} login=${login_code}"

if [[ "${ping_code}" == "200" && "${login_code}" =~ ^(200|302)$ ]]; then
  echo ""
  echo "GREEN: hibs-bet service recovered (ping + login OK)."
  exit 0
fi

if [[ "${ping_code}" == "200" ]]; then
  echo ""
  echo "AMBER: ping OK but login=${login_code} — check auth templates"
  exit 0
fi

warn "recovery incomplete — journalctl -u hibs-bet -n 50"
exit 5

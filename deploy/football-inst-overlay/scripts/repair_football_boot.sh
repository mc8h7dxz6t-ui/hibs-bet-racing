#!/usr/bin/env bash
# hibs-bet won't bind :8000 (curl root=000) — diagnose + common fixes.
#
#   sudo bash /opt/hibs-bet/scripts/repair_football_boot.sh
#   sudo bash /opt/hibs-bet/scripts/repair_football_boot.sh --disable-auth
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

PY="${BET}/.venv/bin/python3"
PIP="${BET}/.venv/bin/pip"

echo "==> hibs-bet unit"
systemctl status hibs-bet --no-pager -l 2>&1 | head -20 || true
echo ""
echo "==> last journal lines"
journalctl -u hibs-bet -n 30 --no-pager 2>&1 | tail -25 || true

touch "${BET}/.env"
grep -q '^HIBS_CACHE_DIR=' "${BET}/.env" 2>/dev/null || echo 'HIBS_CACHE_DIR=/opt/hibs-bet/.cache' >>"${BET}/.env"
grep -q '^HOME=' "${BET}/.env" 2>/dev/null || echo 'HOME=/opt/hibs-bet' >>"${BET}/.env"

if [[ "${DISABLE_AUTH}" -eq 1 ]]; then
  if grep -q '^HIBS_AUTH_ENABLED=' "${BET}/.env"; then
    sed -i 's/^HIBS_AUTH_ENABLED=.*/HIBS_AUTH_ENABLED=0/' "${BET}/.env"
  else
    echo 'HIBS_AUTH_ENABLED=0' >>"${BET}/.env"
  fi
  echo "set HIBS_AUTH_ENABLED=0"
fi

# Auth on without secret key → import crash at startup
if grep -qE '^HIBS_AUTH_ENABLED=1' "${BET}/.env" 2>/dev/null; then
  if ! grep -qE '^HIBS_SECRET_KEY=.+' "${BET}/.env" 2>/dev/null; then
    sk="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
    echo "HIBS_SECRET_KEY=${sk}" >>"${BET}/.env"
    echo "auto-generated HIBS_SECRET_KEY"
  fi
fi

# Production strict startup can refuse boot
if grep -qE '^HIBS_PRODUCTION=1' "${BET}/.env" 2>/dev/null; then
  if ! grep -qE '^HIBS_PREDICTION_LOG_ENABLED=1' "${BET}/.env" 2>/dev/null; then
    echo 'HIBS_PREDICTION_LOG_ENABLED=1' >>"${BET}/.env"
    echo "set HIBS_PREDICTION_LOG_ENABLED=1 (production requires audit log)"
  fi
fi

chown www-data:www-data "${BET}/.env" 2>/dev/null || true

if [[ -x "${PIP}" && -f "${BET}/requirements.txt" ]]; then
  echo "==> pip install (football venv)"
  find "${BET}/.venv/lib" -type d -name '~*' -prune -exec rm -rf {} + 2>/dev/null || true
  sudo -u www-data env HOME="${BET}" PIP_CACHE_DIR="${BET}/.cache/pip" \
    "${PIP}" install -q -r "${BET}/requirements.txt" || true
  sudo -u www-data env HOME="${BET}" PIP_CACHE_DIR="${BET}/.cache/pip" \
    "${PIP}" install -q python-dotenv gunicorn flask werkzeug || true
fi

[[ -x "${PY}" ]] || { echo "ERROR: missing ${PY}" >&2; exit 2; }

echo ""
echo "==> import test (www-data, 120s)"
if ! timeout 120 sudo -u www-data env \
  HOME="${BET}" \
  DEPLOY_PATH="${BET}" \
  PYTHONPATH="${BET}/src:${RACING}/src" \
  HIBS_CACHE_DIR="${BET}/.cache" \
  "${PY}" -c "from hibs_predictor.web import app; print('import ok', app.name)"; then
  echo ""
  echo "IMPORT FAILED — full traceback above / journal:"
  journalctl -u hibs-bet -n 15 --no-pager || true
  exit 3
fi

echo ""
echo "==> restart hibs-bet"
systemctl reset-failed hibs-bet 2>/dev/null || true
systemctl restart hibs-bet
sleep 4

ping="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:8000/api/ping 2>/dev/null || echo 000)"
root="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 12 http://127.0.0.1:8000/ 2>/dev/null || echo 000)"
echo "ping=${ping} root=${root}"

if [[ "${ping}" == "200" ]]; then
  echo "GREEN: hibs-bet is up"
  exit 0
fi

echo "STILL DOWN — run: sudo bash ${BET}/scripts/vps_football_hard_recovery.sh"
exit 4

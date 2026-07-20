#!/usr/bin/env bash
# Repair malformed feature_store.sqlite (RAM disk or persistent path).
#
#   sudo bash /opt/hibs-racing/deploy/repair-feature-store-sqlite.sh
#   sudo bash /opt/hibs-racing/deploy/repair-feature-store-sqlite.sh --check-only
set -euo pipefail

APP="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
CHECK_ONLY=0
for arg in "$@"; do
  case "${arg}" in
    --check-only) CHECK_ONLY=1 ;;
  esac
done

step() { echo ""; echo "==> $*"; }
log() { echo "    $*"; }

[[ -d "${APP}" ]] || { echo "ERROR: ${APP} missing" >&2; exit 1; }
[[ "$(id -u)" -eq 0 ]] || { echo "ERROR: run as root (sudo)" >&2; exit 1; }

if [[ -f "${APP}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${APP}/.env"
  set +a
fi

DB_PATH="${HIBS_RACING_DB_PATH:-${APP}/data/feature_store.sqlite}"
CLI="${APP}/.venv/bin/hibs-racing"
PY="${APP}/.venv/bin/python"

step "feature_store integrity (${DB_PATH})"
if [[ ! -x "${CLI}" ]]; then
  echo "ERROR: ${CLI} missing — run vps_racing_bootstrap.sh" >&2
  exit 1
fi

if [[ "${CHECK_ONLY}" -eq 1 ]]; then
  sudo -u www-data env HOME="${APP}" PYTHONPATH=src HIBS_RACING_DB_PATH="${DB_PATH}" \
    "${CLI}" repair-feature-store --check-only
  exit $?
fi

step "stop hibs-racing (release DB locks)"
systemctl stop hibs-racing 2>/dev/null || true
sleep 2

step "repair feature_store"
sudo -u www-data env HOME="${APP}" PYTHONPATH=src HIBS_RACING_DB_PATH="${DB_PATH}" \
  "${CLI}" repair-feature-store
rc=$?
if [[ "${rc}" -ne 0 ]]; then
  echo "ERROR: repair-feature-store failed (exit ${rc})" >&2
  exit "${rc}"
fi

if [[ -x "${PY}" ]]; then
  ok="$("${PY}" -c "
from pathlib import Path
from hibs_racing.features.db_repair import integrity_check
import os
os.chdir('${APP}')
import sys
sys.path.insert(0, 'src')
chk = integrity_check(Path('${DB_PATH}'))
print('ok' if chk.get('ok') else 'fail')
" 2>/dev/null || echo fail)"
  log "post-repair integrity=${ok}"
fi

step "restart hibs-racing"
systemctl start hibs-racing 2>/dev/null || true
sleep 3
code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:5003/api/ping 2>/dev/null || echo 000)"
log "ping=${code}"
echo ""
echo "Done. Re-run cards refresh if DB was reinitialized:"
echo "  sudo bash ${APP}/scripts/daily_refresh.sh"

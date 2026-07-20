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
  source "${APP}/.env" 2>/dev/null || true
  set +a
fi

DB_PATH="${HIBS_RACING_DB_PATH:-${APP}/data/feature_store.sqlite}"
CLI="${APP}/.venv/bin/hibs-racing"
PY="${APP}/.venv/bin/python"

run_python_repair() {
  local mode="$1"
  sudo -u www-data env HOME="${APP}" PYTHONPATH=src HIBS_RACING_DB_PATH="${DB_PATH}" \
    "${PY}" - <<PY
import json, os, sys
from pathlib import Path
sys.path.insert(0, "src")
from hibs_racing.features.db_repair import integrity_check, repair_feature_store

db = Path(os.environ.get("HIBS_RACING_DB_PATH", "${DB_PATH}"))
check_only = ${mode}
if check_only:
    report = integrity_check(db)
    print(json.dumps(report, indent=2))
    sys.exit(0 if report.get("ok") else 1)
report = repair_feature_store(db)
print(json.dumps(report, indent=2))
sys.exit(0 if report.get("ok") else 1)
PY
}

run_cli_repair() {
  local mode="$1"
  local extra=()
  [[ "${mode}" -eq 1 ]] && extra+=(--check-only)
  sudo -u www-data env HOME="${APP}" PYTHONPATH=src HIBS_RACING_DB_PATH="${DB_PATH}" \
    "${CLI}" repair-feature-store "${extra[@]}"
}

has_cli_repair() {
  [[ -x "${CLI}" ]] && "${CLI}" repair-feature-store --help >/dev/null 2>&1
}

step "feature_store integrity (${DB_PATH})"
if [[ ! -x "${PY}" ]]; then
  echo "ERROR: ${PY} missing — run vps_racing_bootstrap.sh" >&2
  exit 1
fi

if [[ "${CHECK_ONLY}" -eq 1 ]]; then
  if has_cli_repair; then
    run_cli_repair 1
  else
    log "CLI repair-feature-store missing — using Python module"
    run_python_repair 1
  fi
  exit $?
fi

step "stop hibs-racing (release DB locks)"
systemctl stop hibs-racing 2>/dev/null || true
sleep 2

step "repair feature_store"
if has_cli_repair; then
  run_cli_repair 0
else
  log "CLI repair-feature-store missing — using Python module (old deploy)"
  run_python_repair 0
fi
rc=$?
if [[ "${rc}" -ne 0 ]]; then
  echo "ERROR: feature_store repair failed (exit ${rc})" >&2
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

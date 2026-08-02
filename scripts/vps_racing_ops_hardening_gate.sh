#!/usr/bin/env bash
# Racing ops hardening gate — 100% pass required before raceform cron install.
#
#   sudo bash /opt/hibs-racing/scripts/vps_racing_ops_hardening_gate.sh
#   sudo bash /opt/hibs-racing/scripts/vps_racing_ops_hardening_gate.sh --json
set -euo pipefail

APP="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-racing}"
OUT_JSON="${LOG_DIR}/racing-ops-hardening-gate.json"
JSON_ONLY=0

for arg in "$@"; do
  case "${arg}" in
    --json) JSON_ONLY=1 ;;
  esac
done

PY="${APP}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY="python3"
mkdir -p "${LOG_DIR}"
cd "${APP}"

export PYTHONPATH="${APP}/src" HOME="${APP}"

if [[ "${JSON_ONLY}" -eq 1 ]]; then
  "${PY}" "${APP}/scripts/racing_ops_hardening_gate.py" --json | tee "${OUT_JSON}"
else
  "${PY}" "${APP}/scripts/racing_ops_hardening_gate.py" | tee "${OUT_JSON}"
fi

RC=${PIPESTATUS[0]}
chown www-data:www-data "${OUT_JSON}" 2>/dev/null || true
exit "${RC}"

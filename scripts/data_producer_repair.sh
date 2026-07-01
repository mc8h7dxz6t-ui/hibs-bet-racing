#!/usr/bin/env bash
# Racing data producer repair — cards fresh, scrape cycle, daily refresh fallback.
#
#   sudo bash /opt/hibs-racing/scripts/data_producer_repair.sh
#   sudo bash /opt/hibs-racing/scripts/data_producer_repair.sh --dry-run
set -uo pipefail

APP="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-racing}"
DRY=0

for arg in "$@"; do
  [[ "${arg}" == "--dry-run" ]] && DRY=1
done

log() { echo "[racing-data-producer] $*"; }
warn() { echo "[racing-data-producer] WARN: $*" >&2; }

PY="${APP}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY="python3"

mkdir -p "${LOG_DIR}"
export PYTHONPATH="${APP}/src" HOME="${APP}"

SNAP="$("${PY}" -c "
from hibs_racing.data_producer_slo import build_data_producer_snapshot
import json
print(json.dumps(build_data_producer_snapshot()))
" 2>/dev/null || echo '{}')"

printf '%s\n' "${SNAP}" >"${LOG_DIR}/data-producer-slo.json" 2>/dev/null || true

OK="$("${PY}" -c "import json,sys; print(json.loads(sys.argv[1]).get('ok'))" "${SNAP}" 2>/dev/null || echo False)"

log "snapshot ok=${OK}"

if [[ "${OK}" == "True" ]]; then
  log "GREEN — no repair needed"
  exit 0
fi

if [[ ${DRY} -eq 1 ]]; then
  log "dry-run — would run daily_refresh.sh"
  exit 2
fi

if [[ "$(id -u)" -eq 0 && -f "${APP}/scripts/daily_refresh.sh" ]]; then
  log "repair: daily refresh pipeline"
  timeout 1800 bash "${APP}/scripts/daily_refresh.sh" >>"${LOG_DIR}/data-producer-repair.log" 2>&1 || \
    warn "daily refresh failed or timed out (1800s)"
fi

SNAP2="$("${PY}" -c "
from hibs_racing.data_producer_slo import build_data_producer_snapshot
import json
print(json.dumps(build_data_producer_snapshot()))
" 2>/dev/null || echo '{}')"
printf '%s\n' "${SNAP2}" >"${LOG_DIR}/data-producer-slo.json" 2>/dev/null || true
log "post-repair ok=$(printf '%s' "${SNAP2}" | "${PY}" -c "import json,sys; print(json.load(sys.stdin).get('ok'))" 2>/dev/null || echo unknown)"
exit 0

#!/usr/bin/env bash
# Inst++ data producer repair — football cache, FVE export, racing cards.
#
#   sudo bash /opt/hibs-bet/scripts/data_producer_repair.sh
#   sudo bash /opt/hibs-bet/scripts/data_producer_repair.sh --dry-run
set -uo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"
DRY=0

for arg in "$@"; do
  [[ "${arg}" == "--dry-run" ]] && DRY=1
done

log() { echo "[data-producer] $*"; }
warn() { echo "[data-producer] WARN: $*" >&2; }

if [[ -f "${APP}/scripts/lib_hibs_python.sh" ]]; then
  # shellcheck source=lib_hibs_python.sh
  source "${APP}/scripts/lib_hibs_python.sh"
  PY="$(hibs_resolve_python "${APP}")"
else
  PY="${APP}/.venv/bin/python3"
  [[ -x "${PY}" ]] || PY="python3"
fi

mkdir -p "${LOG_DIR}"
export PYTHONPATH="${APP}/src" HOME="${APP}" HIBS_PRODUCTION=1
export HIBS_RACING_DEPLOY_PATH="${RACING}" HIBS_RACING_EVIDENCE_LOCAL="${HIBS_RACING_EVIDENCE_LOCAL:-1}"

SNAP="$("${PY}" -c "
from hibs_predictor.data_producer_slo import build_data_producer_snapshot
import json
print(json.dumps(build_data_producer_snapshot()))
" 2>/dev/null || echo '{}')"

log "snapshot: $(printf '%s' "${SNAP}" | tr -d '\n' | head -c 500)"

NEEDS="$("${PY}" -c "
import json, sys
d = json.loads(sys.argv[1])
sys.exit(0 if not d.get('ok') else 1)
" "${SNAP}" 2>/dev/null; echo $?)"

if [[ "${NEEDS}" != "0" ]]; then
  log "VERDICT: GREEN — no repair needed"
  printf '%s\n' "${SNAP}" >"${LOG_DIR}/data-producer-slo.json"
  exit 0
fi

log "VERDICT: REPAIR — data producer SLO red"

FB_OK="$(printf '%s' "${SNAP}" | "${PY}" -c "import json,sys; d=json.load(sys.stdin); print(d.get('producers',{}).get('football_bundle',{}).get('ok'))")"
HL_OK="$(printf '%s' "${SNAP}" | "${PY}" -c "import json,sys; d=json.load(sys.stdin); print(d.get('producers',{}).get('football_health_light',{}).get('ok'))")"
FVE_EXP="$(printf '%s' "${SNAP}" | "${PY}" -c "import json,sys; d=json.load(sys.stdin); print(d.get('producers',{}).get('fve_lines_export',{}).get('ok'))")"
FVE_REM="$(printf '%s' "${SNAP}" | "${PY}" -c "import json,sys; d=json.load(sys.stdin); print(d.get('producers',{}).get('fve_remote',{}).get('ok'))")"
RC_OK="$(printf '%s' "${SNAP}" | "${PY}" -c "import json,sys; d=json.load(sys.stdin); print(d.get('producers',{}).get('racing_cards',{}).get('ok'))")"

if [[ ${DRY} -eq 1 ]]; then
  log "dry-run — would repair football=${FB_OK} health_light=${HL_OK} fve_export=${FVE_EXP} fve_remote=${FVE_REM} racing=${RC_OK}"
  exit 2
fi

# 1. Football bundle stale / empty — warm cache + throttled restart if health times out
if [[ "${FB_OK}" != "True" || "${HL_OK}" != "True" ]]; then
  log "repair: football fixture cache"
  if [[ -f "${APP}/scripts/warm_football_fixtures.sh" ]]; then
    HOME="${APP}" DEPLOY_PATH="${APP}" \
      HIBS_FIXTURE_WARM_FORCE_REFRESH=1 bash "${APP}/scripts/warm_football_fixtures.sh" \
      >>"${LOG_DIR}/fixture-warm.log" 2>&1 || warn "fixture warm failed"
  elif [[ -f "${APP}/scripts/vps_cache_maintenance.sh" ]]; then
    bash "${APP}/scripts/vps_cache_maintenance.sh" --bust-fixtures 2>/dev/null || true
  fi
  if [[ ! -f "${APP}/scripts/warm_football_fixtures.sh" ]]; then
  "${PY}" -c "
from hibs_predictor.web import fetch_all_fixtures
fetch_all_fixtures(attach_live=False, include_domestic=False, allow_stale=True, force_refresh=True, reboost=True)
print('fixture refresh scheduled')
" 2>/dev/null || warn "fixture force_refresh failed"
  fi
  if [[ "${HL_OK}" != "True" && "$(id -u)" -eq 0 ]]; then
    allowed="$("${PY}" -c "
from hibs_predictor.hands_off_guard import service_restart_allowed
print('yes' if service_restart_allowed('hibs-bet', min_minutes=45) else 'no')
" 2>/dev/null || echo no)"
    if [[ "${allowed}" == "yes" ]]; then
      log "repair: restart hibs-bet (health light failed)"
      systemctl restart hibs-bet 2>/dev/null || true
      sleep 4
    fi
  fi
fi

# 2. FVE lines export empty — re-run collector if script exists on FVE host
if [[ "${FVE_EXP}" != "True" ]]; then
  log "repair: FVE lines export empty — stack wiring"
  if [[ "$(id -u)" -eq 0 && -f "${APP}/deploy/ensure-vps-stack-wiring.sh" ]]; then
    bash "${APP}/deploy/ensure-vps-stack-wiring.sh" --repair || true
  fi
fi

# 3. FVE down/paused — local Docker repair or remote stack wiring
if [[ "${FVE_REM}" != "True" ]]; then
  if [[ "$(id -u)" -eq 0 && -f "${APP}/scripts/lib_fve_local_repair.sh" ]]; then
    # shellcheck source=lib_stack_host.sh
    source "${APP}/scripts/lib_stack_host.sh"
    stack_load_env
    if [[ "${STACK_FVE_LOCAL}" -eq 1 ]]; then
      log "repair: local FVE worker"
      bash "${APP}/scripts/lib_fve_local_repair.sh" || true
    else
      warn "FVE remote not green — run on FVE host: bootstrap-fve-dedicated-1gb.sh"
      if [[ -f "${APP}/deploy/ensure-vps-stack-wiring.sh" ]]; then
        FVE_REMOTE_HOST="${FVE_HOST}" bash "${APP}/deploy/ensure-vps-stack-wiring.sh" --repair || true
      fi
    fi
  fi
fi

# 4. Racing cards stale
if [[ "${RC_OK}" != "True" && -d "${RACING}" ]]; then
  log "repair: racing value lane"
  # shellcheck source=lib_racing_value_lane.sh
  source "${APP}/scripts/lib_racing_value_lane.sh"
  racing_value_lane_matchbook_poll "${RACING}" "${APP}" || true
  if [[ -f "${APP}/scripts/lib_racing_value_lane.sh" ]]; then
    racing_value_lane_run_full "${RACING}" "${APP}" 2>/dev/null || \
      bash "${APP}/deploy/cron-hibs-racing-daily.sh" --run 2>/dev/null || true
  fi
fi

printf '%s\n' "${SNAP}" >"${LOG_DIR}/data-producer-slo.json"
log "repair cycle complete — re-check with: curl -s http://127.0.0.1:8000/api/health?light=1 | head -c 400"
exit 0

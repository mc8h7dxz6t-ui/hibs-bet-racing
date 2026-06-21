#!/usr/bin/env bash
# Institutional++ watchdog — engineering always green; evidence monitored + logged.
#
# Run on VPS (root):
#   sudo bash /opt/hibs-bet/scripts/institutional_vps_watchdog.sh
#   sudo bash /opt/hibs-bet/scripts/institutional_vps_watchdog.sh --repair
#
# From Mac:
#   DEPLOY_HOST=77.68.89.73 ./scripts/institutional_vps_watchdog.sh --remote
set -euo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
TRADING="${TRADING_INSTALL_ROOT:-/opt/trading-core}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"
LOG_FILE="${LOG_DIR}/institutional-watchdog.log"
STATUS_JSON="${LOG_DIR}/institutional-status.json"
REPAIR=0
REMOTE=0

for arg in "$@"; do
  case "${arg}" in
    --repair) REPAIR=1 ;;
    --remote) REMOTE=1 ;;
  esac
done

if [[ "${REMOTE}" -eq 1 ]]; then
  HOST="${DEPLOY_HOST:-77.68.89.73}"
  USER="${DEPLOY_USER:-root}"
  exec ssh -o BatchMode=yes -o ConnectTimeout=25 "${USER}@${HOST}" \
    "export DEPLOY_PATH='${APP}'; bash '${APP}/scripts/institutional_vps_watchdog.sh' --repair"
fi

log() { echo "[inst++] $*"; }
warn() { echo "[inst++] WARN: $*" >&2; }

[[ "$(id -u)" -eq 0 ]] || { echo "run as root on VPS" >&2; exit 1; }
mkdir -p "${LOG_DIR}"
cd "${APP}"
PY="${APP}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY=python3

repair_infra() {
  log "repair: production env + audit flags"
  touch "${APP}/.env"
  for kv in \
    HIBS_PRODUCTION=1 \
    HIBS_PREDICTION_LOG_ENABLED=1 \
    HIBS_CLV_LOG_ENABLED=1; do
    k="${kv%%=*}"
    grep -q "^${k}=" "${APP}/.env" 2>/dev/null || echo "${kv}" >>"${APP}/.env"
  done
  if ! grep -q '^HIBS_EVIDENCE_DEPLOY_DATE=' "${APP}/.env" 2>/dev/null; then
    echo "HIBS_EVIDENCE_DEPLOY_DATE=$(date -u +%Y-%m-%d)" >>"${APP}/.env"
  fi
  chown www-data:www-data "${APP}/.env" 2>/dev/null || true

  log "repair: reinstall ops crons if missing"
  if [[ -f "${APP}/deploy/cron-hibs-ops-automation.sh" ]]; then
    bash "${APP}/deploy/cron-hibs-ops-automation.sh" --install || true
  fi
  if [[ -f "${APP}/deploy/cron-hibs-institutional-watchdog.sh" ]]; then
    bash "${APP}/deploy/cron-hibs-institutional-watchdog.sh" --install || true
  fi

  if [[ -d "${RACING}" ]]; then
    touch "${RACING}/.env"
    for kv in HIBS_DISABLE_UI_REFRESH=1 HIBS_URL_PREFIX=/racing; do
      k="${kv%%=*}"
      grep -q "^${k}=" "${RACING}/.env" 2>/dev/null || echo "${kv}" >>"${RACING}/.env"
    done
    if [[ -f "${APP}/scripts/lib_racing_vps_probe.sh" ]]; then
      # shellcheck source=scripts/lib_racing_vps_probe.sh
      source "${APP}/scripts/lib_racing_vps_probe.sh"
      racing_vps_repair_raceform_env "${RACING}" 2>/dev/null || \
        warn "raceform.db missing — form gates thin until uploaded"
    fi
  fi

  if ! grep -q '^HIBS_HEALTH_RACING_PROBE=' "${APP}/.env" 2>/dev/null; then
    echo "HIBS_HEALTH_RACING_PROBE=1" >>"${APP}/.env"
    log "enabled HIBS_HEALTH_RACING_PROBE=1"
  fi
  if ! grep -q '^HIBS_RACING_EVIDENCE_LOCAL=' "${APP}/.env" 2>/dev/null; then
    echo "HIBS_RACING_EVIDENCE_LOCAL=1" >>"${APP}/.env"
    log "enabled HIBS_RACING_EVIDENCE_LOCAL=1 (faster inst++ racing probes)"
  fi
  if ! grep -q '^HIBS_AUTH_PUBLIC_HEALTH=' "${APP}/.env" 2>/dev/null; then
    echo "HIBS_AUTH_PUBLIC_HEALTH=1" >>"${APP}/.env"
    log "enabled HIBS_AUTH_PUBLIC_HEALTH=1 (unauthenticated /api/health for probes)"
  fi

  if [[ -f "${APP}/deploy/ensure-vps-stack-wiring.sh" ]]; then
    log "repair: stack wiring + .env dedupe"
    bash "${APP}/deploy/ensure-vps-stack-wiring.sh" --repair || warn "stack wiring repair issues"
  fi

  CALIB_CACHE="${APP}/.cache/calibration_v1.json"
  if [[ ! -f "${CALIB_CACHE}" ]]; then
    log "repair: calibration cache missing — running calibration-fit"
    mkdir -p "${APP}/.cache"
    chown www-data:www-data "${APP}/.cache" 2>/dev/null || true
    if HOME="${APP}" PYTHONPATH="${APP}/src" HIBS_PRODUCTION=1 \
      "${PY}" -m hibs_predictor.main calibration-fit >>"${LOG_DIR}/calibration-fit.log" 2>&1; then
      log "calibration-fit OK"
    else
      warn "calibration-fit failed — see ${LOG_DIR}/calibration-fit.log"
    fi
  fi
  if [[ -d "${TRADING}" && -f "${APP}/scripts/vps_sync_trading_core.sh" ]]; then
    log "repair: sync trading-core deploy scripts"
    bash "${APP}/scripts/vps_sync_trading_core.sh" || true
  fi

  log "repair: systemd units (throttled)"
  for unit in hibs-bet hibs-racing trading-shadow-soak; do
    if systemctl is-enabled "${unit}" &>/dev/null; then
      if ! systemctl is-active --quiet "${unit}" 2>/dev/null; then
        allowed="$(HOME="${APP}" PYTHONPATH="${APP}/src" "${PY}" -c "
from hibs_predictor.hands_off_guard import service_restart_allowed
print('yes' if service_restart_allowed('${unit}', min_minutes=45) else 'no')
" 2>/dev/null || echo no)"
        if [[ "${allowed}" == "yes" ]]; then
          warn "restarting ${unit}"
          systemctl reset-failed "${unit}" 2>/dev/null || true
          systemctl restart "${unit}" 2>/dev/null || true
        else
          warn "restart throttled for ${unit} (45m cooldown)"
        fi
      fi
    fi
  done
}

[[ "${REPAIR}" -eq 1 ]] && repair_infra

{
  echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) institutional watchdog ====="
  export PYTHONPATH="${APP}/src" HIBS_PRODUCTION=1 HOME="${APP}"
  export HIBS_RACING_EVIDENCE_LOCAL="${HIBS_RACING_EVIDENCE_LOCAL:-1}"
  export HIBS_RACING_DEPLOY_PATH="${RACING}"

  log "config validation"
  if HOME="${APP}" PYTHONPATH="${APP}/src" HIBS_PRODUCTION=1 \
    "${PY}" scripts/validate_institutional_config.py 2>&1; then
    echo "engineering_config: PASS"
  else
    echo "engineering_config: FAIL"
  fi

  log "institutional readiness"
  HOME="${APP}" PYTHONPATH="${APP}/src" HIBS_PRODUCTION=1 "${PY}" -c "
from hibs_predictor.institutional_readiness import readiness_dict
import json
print(json.dumps(readiness_dict(), indent=2, default=str))
"

  log "football evidence gates"
  if [[ -x "${APP}/scripts/verify_football_evidence_gates.sh" ]]; then
    bash "${APP}/scripts/verify_football_evidence_gates.sh" 2>&1 || true
  fi

  log "calibration drift"
  if HOME="${APP}" PYTHONPATH="${APP}/src" HIBS_PRODUCTION=1 \
    "${PY}" -m hibs_predictor.calibration_drift 2>&1; then
    :
  elif [[ -x "${APP}/scripts/verify_calibration_drift.sh" ]]; then
    HOME="${APP}" DEPLOY_PATH="${APP}" bash "${APP}/scripts/verify_calibration_drift.sh" 2>&1 || true
  fi

  log "racing value-lane SLO"
  if [[ -f "${APP}/scripts/lib_racing_value_lane.sh" ]]; then
    # shellcheck source=scripts/lib_racing_value_lane.sh
    source "${APP}/scripts/lib_racing_value_lane.sh"
    body="$(racing_value_lane_health_json 2>/dev/null || true)"
    if [[ -n "${body}" ]] && racing_value_lane_needs_repair "${body}"; then
      warn "value lane RED"
      if [[ "${REPAIR}" -eq 1 ]]; then
        racing_value_lane_run_full "${RACING}" "${APP}" 2>&1 || true
      fi
    else
      log "value lane SLO green"
    fi
  fi

  log "shadow vs paper reconciliation"
  if [[ -x "${TRADING}/scripts/run_shadow_paper_reconciliation.py" ]]; then
    PYTHONPATH="${TRADING}/src" "${TRADING}/.venv/bin/python3" \
      "${TRADING}/scripts/run_shadow_paper_reconciliation.py" 2>&1 || true
  fi

  log "racing evidence gates"
  export HIBS_RACING_EVIDENCE_LOCAL=1
  export HIBS_RACING_DEPLOY_PATH="${RACING}"
  if [[ -x "${APP}/scripts/verify_racing_evidence_gates.sh" ]]; then
    HOME="${APP}" DEPLOY_PATH="${APP}" bash "${APP}/scripts/verify_racing_evidence_gates.sh" 2>&1 || true
  fi
  if [[ "${REPAIR}" -eq 1 ]] && [[ -x "${APP}/scripts/vps_racing_hard_recovery.sh" ]]; then
    rc_ping="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 8 http://127.0.0.1:5003/api/ping 2>/dev/null || echo 000)"
    if [[ "${rc_ping}" != "200" ]]; then
      warn "racing localhost ping ${rc_ping} — hard recovery"
      export HIBS_BET_DEPLOY_PATH="${APP}" HIBS_RACING_DEPLOY_PATH="${RACING}"
      bash "${APP}/scripts/vps_racing_hard_recovery.sh" 2>&1 || true
      HOME="${APP}" DEPLOY_PATH="${APP}" bash "${APP}/scripts/verify_racing_evidence_gates.sh" 2>&1 || true
    fi
  fi

  log "nine-ten scorecard"
  if [[ -x "${APP}/scripts/score_hibs_nine_ten.sh" ]]; then
    HOME="${APP}" PYTHONPATH="${APP}/src" HIBS_PRODUCTION=1 DEPLOY_PATH="${APP}" \
      bash "${APP}/scripts/score_hibs_nine_ten.sh" 2>&1 || true
  fi

  log "status snapshot -> ${STATUS_JSON}"
  HOME="${APP}" PYTHONPATH="${APP}/src" HIBS_PRODUCTION=1 "${PY}" -c "
import json
from datetime import datetime, timezone
from hibs_predictor.institutional_readiness import readiness_dict
from hibs_predictor.institutional_failsafe import safe_forward_evidence_gates, failsafe_report
try:
    from hibs_predictor.racing_evidence import racing_evidence_gates
    racing = racing_evidence_gates()
except Exception as exc:
    racing = {'buyer_ready': False, 'error': str(exc)[:120]}
try:
    from hibs_predictor.nine_ten_score import score_all
    nine = score_all(remote_production=None, run_remote_verifies=True, run_pytest=False)
except Exception as exc:
    nine = {'institutional_ready': False, 'error': str(exc)[:120]}
try:
    from hibs_predictor.calibration_drift import drift_summary_dict
    cal_drift = drift_summary_dict()
except Exception as exc:
    cal_drift = {'drift_pass': False, 'error': str(exc)[:120]}
try:
    import json as _json
    recon_path = '${TRADING}/data/shadow_paper_recon/latest.json'
    with open(recon_path) as _rf:
        shadow_paper_recon = _json.load(_rf)
except Exception:
    shadow_paper_recon = {}
fwd = safe_forward_evidence_gates()
try:
    failsafe = failsafe_report(app_root='${APP}')
except Exception as exc:
    failsafe = {'failsafe_ok': False, 'error': str(exc)[:120]}
ir = readiness_dict()
out = {
    'ts': datetime.now(timezone.utc).isoformat(),
    'failsafe_ok': bool(failsafe.get('failsafe_ok')),
    'engineering_grade': ir.get('engineering_grade'),
    'evidence_grade': ir.get('evidence_grade'),
    'buyer_ready_football': bool(fwd.get('buyer_ready')),
    'buyer_ready_racing': bool(racing.get('buyer_ready')),
    'institutional_ready': bool(nine.get('institutional_ready')),
    'nine_ten_average': nine.get('average'),
    'matchdays_7d': fwd.get('matchdays_7d'),
    'calibration_drift_pass': bool(cal_drift.get('drift_pass')),
    'shadow_paper_submit_blocked': bool(shadow_paper_recon.get('submit_blocked')),
    'engineering_config_ok': ir.get('engineering_grade') in ('A', 'B+', 'B'),
}
try:
    from hibs_predictor.data_producer_slo import build_data_producer_snapshot
    out['data_producer_ok'] = bool(build_data_producer_snapshot().get('ok'))
except Exception as exc:
    out['data_producer_ok'] = False
    out['data_producer_error'] = str(exc)[:120]
open('${STATUS_JSON}', 'w').write(json.dumps(out, indent=2))
print(json.dumps(out, indent=2))
"

  echo "===== done ====="
} | tee -a "${LOG_FILE}"

chown www-data:www-data "${LOG_FILE}" "${STATUS_JSON}" 2>/dev/null || true

# Exit 0 if engineering is institutional; evidence may still be accumulating.
if HOME="${APP}" PYTHONPATH="${APP}/src" HIBS_PRODUCTION=1 \
  "${PY}" scripts/validate_institutional_config.py >/dev/null 2>&1; then
  log "engineering institutional++ OK (evidence accumulates via cron)"
  exit 0
fi
warn "engineering config issues — see ${LOG_FILE}"
exit 1

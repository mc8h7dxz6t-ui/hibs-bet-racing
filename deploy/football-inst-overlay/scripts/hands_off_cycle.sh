#!/usr/bin/env bash
# Safe hands-off cycle — idempotent, rate-limited, always exit 0 from cron.
#
#   sudo bash /opt/hibs-bet/scripts/hands_off_cycle.sh
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-hands-off.sh --install
set -uo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
TRADING="${TRADING_INSTALL_ROOT:-/opt/trading-core}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"
LOG_FILE="${LOG_DIR}/hands-off-cycle.log"
STATUS_JSON="${LOG_DIR}/hands-off-status.json"
INST_PP_JSON="${LOG_DIR}/inst-pp-status.json"
if [[ -f "${APP}/scripts/lib_hibs_python.sh" ]]; then
  # shellcheck source=lib_hibs_python.sh
  source "${APP}/scripts/lib_hibs_python.sh"
  PY="$(hibs_resolve_python "${APP}")"
else
  PY="${APP}/.venv/bin/python3"
  [[ -x "${PY}" ]] || PY="python3"
fi

log() { echo "[hands-off] $(date -u +%H:%M:%S) $*"; }
warn() { echo "[hands-off] WARN: $*" >&2; }

mkdir -p "${LOG_DIR}"
cd "${APP}" 2>/dev/null || { warn "missing ${APP}"; exit 0; }

# Single-flight — skip if another cycle is running (non-degrading)
if command -v flock >/dev/null 2>&1; then
  exec 9>/var/run/hibs-bet/hands-off-cycle.lock
  mkdir -p /var/run/hibs-bet
  if ! flock -n 9; then
    log "skip — previous cycle still running"
    exit 0
  fi
fi

{
  log "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) hands-off cycle ====="

  export DEPLOY_PATH="${APP}" HIBS_RACING_DEPLOY_PATH="${RACING}" TRADING_INSTALL_ROOT="${TRADING}"
  export PYTHONPATH="${APP}/src" HOME="${APP}" HIBS_PRODUCTION=1
  export HIBS_RACING_EVIDENCE_LOCAL="${HIBS_RACING_EVIDENCE_LOCAL:-1}"
  if command -v hibs_python_env >/dev/null 2>&1; then
    hibs_python_env "${APP}"
  fi

  if [[ "$(id -u)" -eq 0 && -f "${APP}/scripts/lib_football_vps_fallback.sh" ]]; then
    log "infra fallback (probe → soft → hard → nginx)"
    # shellcheck source=lib_football_vps_fallback.sh
    source "${APP}/scripts/lib_football_vps_fallback.sh"
    stack_vps_automation_fallback "${APP}" "${RACING}" || warn "infra fallback — stack not fully green"
  fi

  if [[ "$(id -u)" -eq 0 && -f "${APP}/scripts/vps_sync_trading_core.sh" ]]; then
    log "sync trading-core"
    bash "${APP}/scripts/vps_sync_trading_core.sh" || warn "trading sync failed"
  fi

  if [[ "$(id -u)" -eq 0 && -f "${APP}/deploy/ensure-vps-stack-wiring.sh" ]]; then
    log "stack wiring (repair)"
    bash "${APP}/deploy/ensure-vps-stack-wiring.sh" --repair || warn "stack wiring failed"
  fi

  if [[ "$(id -u)" -eq 0 && -f "${APP}/scripts/institutional_vps_watchdog.sh" ]]; then
    log "institutional watchdog (repair)"
    bash "${APP}/scripts/institutional_vps_watchdog.sh" --repair || warn "watchdog issues"
  fi

  if [[ "$(id -u)" -eq 0 && -f "${APP}/scripts/vps_three_stack_green.sh" ]]; then
    log "three-stack green (repair)"
    bash "${APP}/scripts/vps_three_stack_green.sh" --repair || warn "stack not fully green"
  fi

  if [[ "$(id -u)" -eq 0 && -f "${APP}/scripts/data_producer_repair.sh" ]]; then
    log "data producer SLO (repair)"
    bash "${APP}/scripts/data_producer_repair.sh" || warn "data producer repair issues"
  fi

  if [[ -f "${APP}/scripts/warm_low_source_scrape.sh" ]]; then
    log "low-source scrape (conditional)"
    "${PY}" -c "
import os, subprocess
from hibs_predictor.scrapers.low_source_api import _bundle_fixture_count
from hibs_predictor.scrape_first import scrape_first_mode
n = _bundle_fixture_count(include_domestic=os.getenv('HIBS_FETCH_ALL_DOMESTIC','0').lower() in ('1','true','yes','on'))
if scrape_first_mode() and n < 1:
    subprocess.run(
        ['bash', '${APP}/scripts/warm_low_source_scrape.sh'],
        cwd='${APP}',
        env={**os.environ, 'HOME': '${APP}', 'DEPLOY_PATH': '${APP}', 'LOG_DIR': '${LOG_DIR}'},
        timeout=1200,
        check=False,
    )
    print('low-source scrape triggered — bundle was empty')
else:
    print(f'low-source scrape skipped — bundle_count={n} scrape_first={scrape_first_mode()}')
" 2>&1 || warn "low-source scrape step failed"
  fi

  RACING_WARM="${RACING}/scripts/warm_racing_scrape.sh"
  [[ -f "${RACING_WARM}" ]] || RACING_WARM="${APP}/../scripts/warm_racing_scrape.sh"
  if [[ -f "${RACING_WARM}" ]]; then
    log "racing robust scrape (conditional)"
    "${PY}" -c "
import os, subprocess, json
from urllib import request
racing = os.environ.get('HIBS_RACING_DEPLOY_PATH', '${RACING}')
try:
    with request.urlopen('http://127.0.0.1:5003/api/health', timeout=8) as resp:
        h = json.loads(resp.read().decode())
except Exception:
    h = {}
runners = int(h.get('runners_loaded') or 0)
if runners < 5:
    subprocess.run(
        ['bash', '${RACING_WARM}'],
        cwd=racing,
        env={**os.environ, 'HOME': racing, 'HIBS_RACING_DEPLOY_PATH': racing, 'LOG_DIR': os.environ.get('LOG_DIR', '/var/log/hibs-racing')},
        timeout=900,
        check=False,
    )
    print('racing robust scrape triggered — thin card store')
else:
    print(f'racing scrape skipped — runners_loaded={runners}')
" 2>&1 || warn "racing scrape step failed"
  fi

  log "conditional forward seed"
  "${PY}" -c "
from hibs_predictor.hands_off_guard import (
    capture_pct_7d,
    flock,
    record_seed_forward,
    should_seed_forward,
)
pct = capture_pct_7d()
if should_seed_forward(capture_pct=pct, min_hours=4.0):
    with flock('seed_forward', blocking=False) as acquired:
        if acquired:
            import subprocess
            subprocess.run(
                ['bash', '${APP}/scripts/seed_forward_evidence.sh', '--pipeline-only'],
                cwd='${APP}',
                env={**__import__('os').environ, 'HOME': '${APP}', 'PYTHONPATH': '${APP}/src'},
                timeout=900,
                check=False,
            )
            record_seed_forward()
            print('seeded forward evidence')
        else:
            print('seed skipped — lock held')
else:
    print(f'seed skipped — capture={pct}% or rate limit')
" 2>&1 || warn "seed step failed"

  log "evidence status snapshot"
  if [[ -f "${APP}/scripts/all_evidence_status.py" ]]; then
    "${PY}" "${APP}/scripts/all_evidence_status.py" --json >"${STATUS_JSON}.tmp" 2>/dev/null && \
      mv "${STATUS_JSON}.tmp" "${STATUS_JSON}" || true
  fi

  if [[ -f "${APP}/scripts/alert_f7_capture_regression.py" ]]; then
    "${PY}" "${APP}/scripts/alert_f7_capture_regression.py" 2>&1 || true
  fi

  log "inst++ automation snapshot (lightweight)"
  if [[ -f "${APP}/src/hibs_predictor/inst_pp_snapshot.py" ]]; then
    "${PY}" -c "
from hibs_predictor.inst_pp_snapshot import build_inst_pp_snapshot, write_status_json
snap = build_inst_pp_snapshot(include_nine_ten=False)
write_status_json('${INST_PP_JSON}', snap)
print('inst_pp_tier', snap.get('inst_pp_tier'), 'auto_ok', (snap.get('automation_health') or {}).get('ok'))
" 2>&1 || warn "inst++ snapshot failed"
  fi

  log "done"
} >>"${LOG_FILE}" 2>&1

chown www-data:www-data "${LOG_FILE}" "${STATUS_JSON}" "${INST_PP_JSON}" 2>/dev/null || true
exit 0

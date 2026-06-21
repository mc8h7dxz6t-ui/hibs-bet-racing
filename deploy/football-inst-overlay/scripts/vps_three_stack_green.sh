#!/usr/bin/env bash
# Football + Racing + Trading — repair, verify, log. Hands-off operations.
#
# VPS (root):
#   bash /opt/hibs-bet/scripts/vps_three_stack_green.sh --repair
#
# Mac:
#   DEPLOY_HOST=77.68.89.73 ./scripts/vps_three_stack_green.sh --remote --repair
set -euo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
TRADING="${TRADING_INSTALL_ROOT:-/opt/trading-core}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"
LOG_FILE="${LOG_DIR}/three-stack-green.log"
STATUS_JSON="${LOG_DIR}/three-stack-status.json"
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
  extra=""
  [[ "${REPAIR}" -eq 1 ]] && extra="--repair"
  exec ssh -o BatchMode=yes -o ConnectTimeout=30 "${USER}@${HOST}" \
    "export DEPLOY_PATH='${APP}' HIBS_RACING_DEPLOY_PATH='${RACING}' TRADING_INSTALL_ROOT='${TRADING}'; \
     bash '${APP}/scripts/vps_three_stack_green.sh' ${extra}"
fi

log() { echo "[3stack] $*"; }
warn() { echo "[3stack] WARN: $*" >&2; }

[[ "$(id -u)" -eq 0 ]] || { echo "run as root on VPS" >&2; exit 1; }
mkdir -p "${LOG_DIR}"
PY="${APP}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY=python3

football_ok=0
racing_ok=0
trading_ok=0
lines_ok=0
fail=0
FVE_HOST="${FVE_REMOTE_HOST:-127.0.0.1}"
FVE_PORT="${FVE_API_PORT:-8010}"
if [[ -f /etc/hibs-bet/stack.env ]]; then
  # shellcheck disable=SC1091
  source /etc/hibs-bet/stack.env
  FVE_HOST="${FVE_REMOTE_HOST:-${FVE_HOST}}"
fi

probe_http() {
  curl -sS -o /dev/null -w '%{http_code}' --max-time "${2:-12}" "$1" 2>/dev/null || echo 000
}

repair_all() {
  log "repair: full VPS automation"
  if [[ -f "${APP}/scripts/_vps_automation_remote.sh" ]]; then
    export DEPLOY_PATH="${APP}" HIBS_RACING_DEPLOY_PATH="${RACING}" TRADING_INSTALL_ROOT="${TRADING}"
    bash "${APP}/scripts/_vps_automation_remote.sh" || true
  fi
  if [[ -f "${APP}/deploy/apply-vps-trading-link.sh" ]]; then
    export DEPLOY_PATH="${APP}"
    bash "${APP}/deploy/apply-vps-trading-link.sh" 2>/dev/null || true
  fi
  if [[ -d "${RACING}" && -f "${APP}/scripts/vps_racing_hard_recovery.sh" ]]; then
    log "repair: racing hard recovery (502 / stuck :5003)"
    export HIBS_BET_DEPLOY_PATH="${APP}" HIBS_RACING_DEPLOY_PATH="${RACING}"
    bash "${APP}/scripts/vps_racing_hard_recovery.sh" || true
    if [[ -f "${APP}/deploy/apply-vps-racing-link.sh" ]]; then
      export DEPLOY_PATH="${APP}" HIBS_RACING_DEPLOY_PATH="${RACING}"
      bash "${APP}/deploy/apply-vps-racing-link.sh" 2>/dev/null || true
    fi
  fi
  if [[ -d "${RACING}" && -f "${APP}/scripts/lib_racing_value_lane.sh" ]]; then
    if curl -fsS --max-time 8 "http://127.0.0.1:5003/api/health" 2>/dev/null | \
      python3 -c "import json,sys; h=json.load(sys.stdin); exit(0 if int(h.get('unscored_runners') or 0)>0 or h.get('nan_integrity_passed') is False or h.get('db_ui_in_sync') is False else 1)" 2>/dev/null; then
      log "repair: racing value lane (unscored / nan / sync)"
      export HIBS_BET_DEPLOY_PATH="${APP}" HIBS_RACING_DEPLOY_PATH="${RACING}"
      # shellcheck source=lib_racing_value_lane.sh
      source "${APP}/scripts/lib_racing_value_lane.sh"
      racing_value_lane_run_full "${RACING}" "${APP}" || true
    fi
  fi
  if [[ -f "${APP}/scripts/lib_fve_local_repair.sh" ]]; then
    log "repair: line shopper / FVE local"
    bash "${APP}/scripts/lib_fve_local_repair.sh" || true
  fi
}

[[ "${REPAIR}" -eq 1 ]] && repair_all

{
  echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) three-stack green ====="

  log "FOOTBALL hibs-bet"
  fb_unit="$(systemctl is-active hibs-bet 2>/dev/null || echo inactive)"
  echo "  unit: ${fb_unit}"
  if [[ "${fb_unit}" != "active" ]]; then
    if HOME="${APP}" PYTHONPATH="${APP}/src" "${PY}" -c "
from hibs_predictor.hands_off_guard import service_restart_allowed
import sys
sys.exit(0 if service_restart_allowed('hibs-bet', min_minutes=45) else 1)
" 2>/dev/null; then
      warn "restarting hibs-bet"
      systemctl reset-failed hibs-bet 2>/dev/null || true
      systemctl restart hibs-bet 2>/dev/null || true
      sleep 4
    else
      warn "hibs-bet restart throttled (45m cooldown)"
    fi
    fb_unit="$(systemctl is-active hibs-bet 2>/dev/null || echo inactive)"
  fi
  fb_ping="$(probe_http http://127.0.0.1:8000/api/ping 15)"
  echo "  ping: ${fb_ping}"
  fb_api=0
  fb_api_optional=0
  if [[ -f "${APP}/.env" ]] && grep -qE '^HIBS_DISABLE_API_SPORTS=1' "${APP}/.env" 2>/dev/null; then
    fb_api_optional=1
    echo "  api_football: skipped (HIBS_DISABLE_API_SPORTS=1 scrape-first)"
    fb_api=1
  elif HOME="${APP}" PYTHONPATH="${APP}/src" HIBS_PRODUCTION=1 "${PY}" -c "
from hibs_predictor.health_probe import gather_health
row = next((a for a in gather_health().get('apis', []) if a.get('id') == 'api_football'), {})
exit(0 if row.get('ok') else 1)
" 2>/dev/null; then
    fb_api=1
    echo "  api_football: ok"
  else
    echo "  api_football: FAIL (quota/key — or run deploy/apply-vps-scrape-first.sh)"
  fi
  if [[ "${fb_unit}" == "active" && "${fb_ping}" == "200" && "${fb_api}" -eq 1 ]]; then
    football_ok=1
    echo "  FOOTBALL: GREEN"
  else
    echo "  FOOTBALL: RED"
    fail=1
  fi

  echo ""
  log "RACING hibs-racing"
  rc_unit="$(systemctl is-active hibs-racing 2>/dev/null || echo inactive)"
  echo "  unit: ${rc_unit}"
  if [[ "${rc_unit}" != "active" && -d "${RACING}" ]]; then
    if HOME="${APP}" PYTHONPATH="${APP}/src" "${PY}" -c "
from hibs_predictor.hands_off_guard import service_restart_allowed
import sys
sys.exit(0 if service_restart_allowed('hibs-racing', min_minutes=45) else 1)
" 2>/dev/null; then
      warn "restarting hibs-racing"
      systemctl reset-failed hibs-racing 2>/dev/null || true
      systemctl restart hibs-racing 2>/dev/null || true
      sleep 8
    else
      warn "hibs-racing restart throttled (45m cooldown)"
    fi
    rc_unit="$(systemctl is-active hibs-racing 2>/dev/null || echo inactive)"
  fi
  rc_ping="$(probe_http http://127.0.0.1:5003/api/ping 20)"
  echo "  ping: ${rc_ping}"
  rc_db=0
  if [[ -f "${RACING}/data/feature_store.sqlite" ]]; then
    rc_db=1
    echo "  feature_store: $(du -h "${RACING}/data/feature_store.sqlite" | awk '{print $1}')"
  elif [[ -f "${APP}/scripts/lib_racing_vps_probe.sh" ]]; then
    # shellcheck source=scripts/lib_racing_vps_probe.sh
    source "${APP}/scripts/lib_racing_vps_probe.sh"
    if racing_vps_sqlite_has_cards "${RACING}" 2>/dev/null; then
      rc_db=1
      echo "  sqlite: has card rows"
    else
      echo "  sqlite: no cards — cron will refresh at 06/12/17 UTC"
    fi
  fi
  if [[ "${rc_unit}" == "active" && "${rc_ping}" == "200" ]]; then
    racing_ok=1
    echo "  RACING: GREEN"
  elif [[ "${rc_unit}" == "active" && "${rc_ping}" != "200" ]]; then
    echo "  RACING: RED (unit active but ping ${rc_ping} — site shows 502)"
    if [[ "${REPAIR}" -eq 1 && -f "${APP}/scripts/vps_racing_hard_recovery.sh" ]]; then
      warn "hard recovery racing"
      export HIBS_BET_DEPLOY_PATH="${APP}" HIBS_RACING_DEPLOY_PATH="${RACING}"
      bash "${APP}/scripts/vps_racing_hard_recovery.sh" || true
      sleep 5
      rc_ping="$(probe_http http://127.0.0.1:5003/api/ping 25)"
      echo "  ping after recovery: ${rc_ping}"
      [[ "${rc_ping}" == "200" ]] && racing_ok=1 && echo "  RACING: GREEN"
    fi
    [[ "${racing_ok}" -eq 1 ]] || fail=1
  else
    echo "  RACING: RED"
    fail=1
  fi

  echo ""
  log "TRADING shadow soak"
  tr_unit="$(systemctl is-active trading-shadow-soak 2>/dev/null || echo inactive)"
  echo "  unit: ${tr_unit}"
  if [[ "${tr_unit}" != "active" && -f "${TRADING}/deploy/install-harvested-execution-shadow.sh" ]]; then
    warn "starting trading-shadow-soak"
    systemctl stop trading-paper 2>/dev/null || true
    cd "${TRADING}"
    TRADING_INSTALL_ROOT="${TRADING}" bash deploy/install-harvested-execution-shadow.sh --install-root "${TRADING}" 2>/dev/null || true
    tr_unit="$(systemctl is-active trading-shadow-soak 2>/dev/null || echo inactive)"
  fi
  if [[ "${REPAIR}" -eq 1 && -f "${APP}/deploy/apply-vps-trading-crypto-lane.sh" ]]; then
    if ! grep -qE '^TRADING_ENABLE_CRYPTO=1' /etc/trading_secrets 2>/dev/null; then
      warn "enabling crypto lane (BTC/USD,ETH/USD)"
      export DEPLOY_PATH="${APP}"
      bash "${APP}/deploy/apply-vps-trading-crypto-lane.sh" 2>/dev/null || true
      sleep 5
    fi
  fi
  tr_live="$(probe_http http://127.0.0.1:9108/live 8)"
  tr_ready="$(probe_http http://127.0.0.1:9108/ready 8)"
  echo "  metrics live: ${tr_live} ready: ${tr_ready}"
  if [[ "${tr_unit}" == "active" && ( "${tr_live}" == "200" || "${tr_ready}" == "200" ) ]]; then
    trading_ok=1
    echo "  TRADING: GREEN"
  elif [[ "${tr_unit}" == "active" ]]; then
    trading_ok=1
    echo "  TRADING: AMBER (unit active, metrics warming)"
  else
    echo "  TRADING: RED"
    fail=1
  fi

  echo ""
  log "LINE SHOPPER / FVE (arb)"
  fve_health="$(probe_http "http://${FVE_HOST}:${FVE_PORT}/health" 10)"
  echo "  fve health: ${fve_health} @ ${FVE_HOST}:${FVE_PORT}"
  fve_worker=0
  if [[ "${fve_health}" == "200" ]]; then
    if curl -fsS --max-time 8 "http://${FVE_HOST}:${FVE_PORT}/health" 2>/dev/null | \
      python3 -c "import json,sys; d=json.load(sys.stdin); w=d.get('worker') or {}; sys.exit(0 if w.get('alive') else 1)" 2>/dev/null; then
      fve_worker=1
      echo "  worker: alive"
    else
      echo "  worker: not alive"
      if [[ "${REPAIR}" -eq 1 && -f "${APP}/scripts/lib_fve_local_repair.sh" ]]; then
        bash "${APP}/scripts/lib_fve_local_repair.sh" || true
        sleep 4
        if curl -fsS --max-time 8 "http://${FVE_HOST}:${FVE_PORT}/health" 2>/dev/null | \
          python3 -c "import json,sys; d=json.load(sys.stdin); w=d.get('worker') or {}; sys.exit(0 if w.get('alive') else 1)" 2>/dev/null; then
          fve_worker=1
          echo "  worker: alive after repair"
        fi
      fi
    fi
  elif [[ "${REPAIR}" -eq 1 && -f "${APP}/scripts/lib_fve_local_repair.sh" ]]; then
    bash "${APP}/scripts/lib_fve_local_repair.sh" || true
    fve_health="$(probe_http "http://${FVE_HOST}:${FVE_PORT}/health" 10)"
    echo "  fve health after repair: ${fve_health}"
    [[ "${fve_health}" == "200" ]] && fve_worker=1
  fi
  fve_fixtures="$(curl -fsS --max-time 10 http://127.0.0.1:8000/api/fve/fixtures 2>/dev/null | \
    python3 -c 'import json,sys; d=json.load(sys.stdin); print(int(d.get("count") or 0))' 2>/dev/null || echo 0)"
  echo "  fve fixtures export: ${fve_fixtures}"
  if [[ "${fve_health}" == "200" && "${fve_worker}" -eq 1 ]]; then
    lines_ok=1
    echo "  LINE SHOPPER: GREEN"
  elif [[ "${fve_health}" == "200" ]]; then
    lines_ok=1
    echo "  LINE SHOPPER: AMBER (API up, worker warming)"
  else
    echo "  LINE SHOPPER: RED"
    fail=1
  fi

  echo ""
  log "crons"
  crontab -u www-data -l 2>/dev/null | grep -cE 'hibs-bet|hibs-racing|institutional' || echo "0"

  HOME="${APP}" PYTHONPATH="${APP}/src" HIBS_PRODUCTION=1 "${PY}" -c "
import json
from datetime import datetime, timezone
out = {
  'ts': datetime.now(timezone.utc).isoformat(),
  'football_green': ${football_ok} == 1,
  'racing_green': ${racing_ok} == 1,
  'trading_green': ${trading_ok} == 1,
  'lines_green': ${lines_ok} == 1,
  'all_green': ${football_ok} == 1 and ${racing_ok} == 1 and ${trading_ok} == 1 and ${lines_ok} == 1,
  'football_ping': '${fb_ping}',
  'racing_ping': '${rc_ping}',
  'trading_live': '${tr_live}',
  'fve_health': '${fve_health}',
  'fve_fixtures': '${fve_fixtures}',
}
open('${STATUS_JSON}', 'w').write(json.dumps(out, indent=2))
print(json.dumps(out, indent=2))
"

  echo "===== summary: football=${football_ok} racing=${racing_ok} trading=${trading_ok} lines=${lines_ok} ====="
} | tee -a "${LOG_FILE}"

chown www-data:www-data "${LOG_FILE}" "${STATUS_JSON}" 2>/dev/null || true

if [[ "${fail}" -eq 0 ]]; then
  log "FOUR STACK: GREEN"
  exit 0
fi
warn "FOUR STACK: issues — will retry on next cron cycle"
exit 1

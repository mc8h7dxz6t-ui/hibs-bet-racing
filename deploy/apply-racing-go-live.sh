#!/usr/bin/env bash
# Racing go-live: production profile + McFadden win engine + trading daemon configs.
#
#   sudo bash /opt/hibs-racing/deploy/apply-racing-go-live.sh
#   sudo bash /opt/hibs-racing/deploy/apply-racing-go-live.sh --inactive   # rollback env flag only
#
set -euo pipefail

RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
BET="${HIBS_BET_DEPLOY_PATH:-/opt/hibs-bet}"
ACTIVE=1
SEED_CALIBRATION=1

for arg in "$@"; do
  case "${arg}" in
    --active) ACTIVE=1 ;;
    --inactive) ACTIVE=0 ;;
    --no-seed) SEED_CALIBRATION=0 ;;
    -h|--help)
      sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
  esac
done

[[ "$(id -u)" -eq 0 ]] || { echo "run as root on VPS" >&2; exit 1; }
[[ -d "${RACING}/src" ]] || { echo "missing ${RACING} — sync racing first" >&2; exit 1; }

log() { echo "[racing-go-live] $*"; }
warn() { echo "[racing-go-live] WARN: $*" >&2; }

log "1/7 production racing profile"
if [[ -f "${RACING}/deploy/apply-vps-production-racing.sh" ]]; then
  bash "${RACING}/deploy/apply-vps-production-racing.sh"
else
  warn "apply-vps-production-racing.sh missing"
fi

log "2/7 McFadden win engine env"
if [[ "${ACTIVE}" -eq 1 ]]; then
  bash "${RACING}/deploy/apply-win-engine-env.sh" --active
else
  bash "${RACING}/deploy/apply-win-engine-env.sh" --inactive
fi

log "3/7 trading daemon + flight-latency guard configs (simulation only)"
if [[ -f "${RACING}/deploy/apply-trading-daemon.sh" ]]; then
  bash "${RACING}/deploy/apply-trading-daemon.sh" --enable
fi

log "4/7 RAM disk + hard recovery"
if [[ -f "${BET}/deploy/mount-hibs-ramdisk.sh" ]]; then
  bash "${BET}/deploy/mount-hibs-ramdisk.sh" 2>/dev/null || true
fi
if [[ -f "${BET}/scripts/vps_racing_hard_recovery.sh" ]]; then
  export HIBS_BET_DEPLOY_PATH="${BET}" HIBS_RACING_DEPLOY_PATH="${RACING}"
  bash "${BET}/scripts/vps_racing_hard_recovery.sh" || warn "racing hard recovery incomplete"
fi

if [[ "${SEED_CALIBRATION}" -eq 1 && "${ACTIVE}" -eq 1 ]]; then
  log "5/7 seed win_engine_calibration (OOS backtest — does not bypass circuit)"
  if [[ -f "${RACING}/deploy/cron-hibs-win-engine-backtest.sh" ]]; then
    bash "${RACING}/deploy/cron-hibs-win-engine-backtest.sh" || warn "win-engine backtest seed failed"
  else
    warn "cron-hibs-win-engine-backtest.sh missing"
  fi
else
  log "5/7 seed skipped"
fi

log "6/7 daily refresh + sandbox scoring pass"
PY="${RACING}/.venv/bin/hibs-racing"
[[ -x "${PY}" ]] || PY="$(command -v hibs-racing || true)"
if [[ -n "${PY}" ]]; then
  if [[ -f "${BET}/deploy/cron-hibs-racing-daily.sh" ]]; then
    HIBS_RACING_DEPLOY_PATH="${RACING}" bash "${BET}/deploy/cron-hibs-racing-daily.sh" --run || \
      warn "racing daily refresh failed — check credentials"
  fi
  sudo -u www-data env HOME="${RACING}" PYTHONPATH="${RACING}/src:${BET}/src" \
    HIBS_RACING_DB_PATH="${RACING}/data/feature_store.sqlite" \
    "${PY}" refresh-cards --workers 1 2>/dev/null || warn "refresh-cards failed"
else
  warn "hibs-racing CLI not found"
fi

log "7/7 verify"
systemctl restart hibs-racing 2>/dev/null || true
sleep 4
RC="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 http://127.0.0.1:5003/api/ping 2>/dev/null || echo 000)"
echo "  hibs-racing ping: ${RC}"
if [[ -f "${RACING}/scripts/verify_win_engine_deploy.sh" ]]; then
  HIBS_PRODUCTION_URL="${HIBS_PRODUCTION_URL:-http://127.0.0.1:8000}" \
    HIBS_RACING_DB_PATH="${RACING}/data/feature_store.sqlite" \
    bash "${RACING}/scripts/verify_win_engine_deploy.sh" || warn "win engine verify issues"
fi

echo ""
echo "========== RACING GO-LIVE APPLIED =========="
echo "HIBS_WIN_ENGINE_ACTIVE=$([[ ${ACTIVE} -eq 1 ]] && echo true || echo false)"
echo "Public win-engine API releases only when calibration_state=CALIBRATED"
echo "Check: sqlite3 ${RACING}/data/feature_store.sqlite \"SELECT * FROM win_engine_calibration;\""

#!/usr/bin/env bash
# ONE COMMAND — autonomous Inst++ on consolidated VPS (87.106.100.52 / hibs-bet.co.uk).
#
# Arms all crons, scrape-first profiles, data repair, and prediction-results collection
# across Football · Racing · Trading · Lines — no manual warm loops.
#
# Run on VPS as root:
#   sudo bash /opt/hibs-racing/deploy/vps-autonomous-install.sh
#
# From Mac (SSH):
#   DEPLOY_HOST=87.106.100.52 bash deploy/vps-autonomous-install.sh --remote
#
# Options:
#   --skip-sync       use on-disk code only
#   --skip-repair     crons + profiles only (no warm/repair)
#   --remote          SSH to DEPLOY_HOST and run there
set -euo pipefail

BET="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
TRADING="${TRADING_INSTALL_ROOT:-/opt/trading-core}"
PUBLIC="${HIBS_PUBLIC_HOST:-hibs-bet.co.uk}"
VPS_IP="${HIBS_VPS_IP:-87.106.100.52}"
RACING_REF="${HIBS_RACING_SYNC_REF:-cursor/robust-scrape-inst-7e4d}"
FOOTBALL_REF="${HIBS_SYNC_REF:-main}"
REMOTE=0
SKIP_SYNC=0
SKIP_REPAIR=0

for arg in "$@"; do
  case "${arg}" in
    --remote) REMOTE=1 ;;
    --skip-sync) SKIP_SYNC=1 ;;
    --skip-repair) SKIP_REPAIR=1 ;;
  esac
done

if [[ "${REMOTE}" -eq 1 ]]; then
  HOST="${DEPLOY_HOST:-${VPS_IP}}"
  USER="${DEPLOY_USER:-root}"
  flags=""
  [[ "${SKIP_SYNC}" -eq 1 ]] && flags="${flags} --skip-sync"
  [[ "${SKIP_REPAIR}" -eq 1 ]] && flags="${flags} --skip-repair"
  exec ssh -o BatchMode=yes -o ConnectTimeout=30 "${USER}@${HOST}" \
    "export DEPLOY_PATH='${BET}' HIBS_RACING_DEPLOY_PATH='${RACING}' TRADING_INSTALL_ROOT='${TRADING}' \
     HIBS_PUBLIC_HOST='${PUBLIC}' HIBS_VPS_IP='${VPS_IP}' \
     HIBS_RACING_SYNC_REF='${RACING_REF}' HIBS_SYNC_REF='${FOOTBALL_REF}'; \
     bash '${RACING}/deploy/vps-autonomous-install.sh' ${flags}"
fi

step() { echo ""; echo "========== $* =========="; }
warn() { echo "[autonomous] WARN: $*" >&2; }

[[ "$(id -u)" -eq 0 ]] || { echo "run as root on VPS: sudo bash $0" >&2; exit 1; }

step "0) Log dirs + stack.env"
mkdir -p /var/log/hibs-bet /var/log/hibs-racing /var/run/hibs-bet /var/run/hibs-racing /etc/hibs-bet
cat >/etc/hibs-bet/stack.env <<EOF
FVE_REMOTE_HOST=127.0.0.1
HIBS_PUBLIC_HOST=${PUBLIC}
HIBS_VPS_IP=${VPS_IP}
EOF

if [[ "${SKIP_SYNC}" -eq 0 ]]; then
  step "1a) Sync racing from GitHub (${RACING_REF})"
  if [[ -f "${BET}/deploy/vps-sync-racing-from-github.sh" ]]; then
    HIBS_RACING_SYNC_REF="${RACING_REF}" HIBS_RACING_DEPLOY_PATH="${RACING}" \
      bash "${BET}/deploy/vps-sync-racing-from-github.sh" || warn "racing sync failed"
  elif [[ -f "${RACING}/deploy/vps-sync-racing-from-github.sh" ]]; then
    HIBS_RACING_SYNC_REF="${RACING_REF}" HIBS_RACING_DEPLOY_PATH="${RACING}" \
      bash "${RACING}/deploy/vps-sync-racing-from-github.sh" || warn "racing sync failed"
  else
    warn "no vps-sync-racing-from-github.sh — using on-disk ${RACING}"
  fi

  step "1b) Sync football baseline from GitHub (${FOOTBALL_REF})"
  if [[ -f "${BET}/deploy/vps-sync-from-github.sh" ]]; then
    HIBS_SYNC_REF="${FOOTBALL_REF}" APP_ROOT="${BET}" \
      bash "${BET}/deploy/vps-sync-from-github.sh" || warn "football github sync failed"
  else
    warn "football sync script missing — overlay only"
  fi
else
  step "1) Skip sync (--skip-sync)"
fi

step "2) Football Inst++ overlay (robust scrape branch delta)"
if [[ -f "${RACING}/deploy/vps-sync-football-inst-overlay.sh" ]]; then
  OVERLAY_ROOT="${RACING}/deploy/football-inst-overlay" \
    bash "${RACING}/deploy/vps-sync-football-inst-overlay.sh"
elif [[ -f "${BET}/deploy/vps-sync-football-inst-overlay.sh" ]]; then
  bash "${BET}/deploy/vps-sync-football-inst-overlay.sh"
else
  warn "football overlay missing — inst scrape code may be stale on main"
fi

step "3) Institutional profiles (scrape-first, prediction logging)"
if [[ -f "${BET}/deploy/apply-vps-scrape-first-institutional.sh" ]]; then
  bash "${BET}/deploy/apply-vps-scrape-first-institutional.sh"
else
  warn "apply-vps-scrape-first-institutional.sh missing"
fi
if [[ -f "${RACING}/deploy/apply-vps-racing-scrape-first-institutional.sh" ]]; then
  bash "${RACING}/deploy/apply-vps-racing-scrape-first-institutional.sh"
elif [[ -f "${BET}/../deploy/apply-vps-racing-scrape-first-institutional.sh" ]]; then
  bash "${BET}/../deploy/apply-vps-racing-scrape-first-institutional.sh"
fi

touch "${BET}/.env"
for kv in \
  HIBS_PRODUCTION=1 \
  HIBS_PREDICTION_LOG_ENABLED=1 \
  HIBS_CLV_LOG_ENABLED=1 \
  HIBS_PREDICTION_LOG_ALWAYS=1 \
  HIBS_AUDIT_SETTLE_SCRAPE_FALLBACK=1 \
  HIBS_HEALTH_RACING_PROBE=1 \
  HIBS_HEALTH_TRADING_DAY15=1 \
  HIBS_RACING_EVIDENCE_LOCAL=1; do
  k="${kv%%=*}"
  grep -q "^${k}=" "${BET}/.env" 2>/dev/null || echo "${kv}" >>"${BET}/.env"
done
grep -q '^HIBS_EVIDENCE_DEPLOY_DATE=' "${BET}/.env" 2>/dev/null || \
  echo "HIBS_EVIDENCE_DEPLOY_DATE=$(date -u +%Y-%m-%d)" >>"${BET}/.env"
chown www-data:www-data "${BET}/.env" 2>/dev/null || true

step "4) Arm all platform crons"
if [[ -f "${BET}/scripts/install_all_platform_automation.sh" ]]; then
  HIBS_SYNC_REF="${FOOTBALL_REF}" DEPLOY_PATH="${BET}" HIBS_RACING_DEPLOY_PATH="${RACING}" \
    TRADING_INSTALL_ROOT="${TRADING}" HIBS_PUBLIC_HOST="${PUBLIC}" HIBS_VPS_IP="${VPS_IP}" \
    bash "${BET}/scripts/install_all_platform_automation.sh" --skip-sync || warn "install_all_platform partial"
elif [[ -f "${BET}/scripts/install_hands_off_automation.sh" ]]; then
  bash "${BET}/scripts/install_hands_off_automation.sh" || warn "hands-off install partial"
fi

# Racing scrape cron (lives in racing deploy/)
if [[ -f "${RACING}/deploy/cron-hibs-racing-scrape.sh" ]]; then
  bash "${RACING}/deploy/cron-hibs-racing-scrape.sh" --install || true
fi

# Cross-platform prediction results
PRED_CRON="${BET}/deploy/cron-hibs-prediction-results-all.sh"
[[ -f "${PRED_CRON}" ]] || PRED_CRON="${RACING}/deploy/cron-hibs-prediction-results-all.sh"
if [[ -f "${PRED_CRON}" ]]; then
  bash "${PRED_CRON}" --install || true
fi

step "5) Stack wiring + trading shadow"
if [[ -f "${BET}/deploy/ensure-vps-stack-wiring.sh" ]]; then
  bash "${BET}/deploy/ensure-vps-stack-wiring.sh" --repair || true
fi
if [[ -f "${BET}/scripts/vps_sync_trading_core.sh" ]]; then
  bash "${BET}/scripts/vps_sync_trading_core.sh" || true
fi

if [[ "${SKIP_REPAIR}" -eq 0 ]]; then
  step "6) Full data repair + warm"
  if [[ -f "${BET}/deploy/vps-full-data-repair.sh" ]]; then
    bash "${BET}/deploy/vps-full-data-repair.sh" || warn "full data repair had warnings"
  else
    [[ -f "${BET}/deploy/vps-warm-and-verify.sh" ]] && \
      bash "${BET}/deploy/vps-warm-and-verify.sh" --warm-only || true
    [[ -f "${RACING}/scripts/warm_racing_scrape.sh" ]] && \
      HOME="${RACING}" bash "${RACING}/scripts/warm_racing_scrape.sh" || true
  fi

  step "7) Prediction results now (don't wait for cron)"
  [[ -f "${PRED_CRON}" ]] && bash "${PRED_CRON}" --run || true

  step "8) Hands-off cycle"
  [[ -f "${BET}/scripts/hands_off_cycle.sh" ]] && bash "${BET}/scripts/hands_off_cycle.sh" || true
else
  step "6-8) Skip repair (--skip-repair)"
fi

step "9) Verify"
PY="${BET}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY=python3

echo "--- football ping ---"
curl -sS --max-time 8 http://127.0.0.1:8000/api/ping 2>/dev/null | head -c 300 || warn "football ping"
echo ""
echo "--- racing ping ---"
curl -sS --max-time 8 http://127.0.0.1:5003/api/ping 2>/dev/null | head -c 300 || warn "racing ping"
echo ""

if [[ -f "${BET}/scripts/verify_inst_pp_automation.sh" ]]; then
  bash "${BET}/scripts/verify_inst_pp_automation.sh" || warn "inst++ verify gaps"
fi

HOME="${BET}" PYTHONPATH="${BET}/src" "${PY}" -c "
from hibs_predictor.data_producer_slo import build_data_producer_snapshot
import json
print(json.dumps(build_data_producer_snapshot(), indent=2, default=str))
" 2>/dev/null | tee /var/log/hibs-bet/data-producer-slo.json || true

cat <<EOF

========== AUTONOMOUS INST++ ARMED ==========

Products (self-healing every 30m + scrape crons):

  Football   https://${PUBLIC}/
  Racing     https://${PUBLIC}/racing/
  Trading    https://${PUBLIC}/harvested-execution
  Lines      https://${PUBLIC}/line-trader

Prediction results (automatic):
  Football   daily audit 06:35 + 23:05 UTC + midday/evening catch-up
  Racing     score-card + settle-paper + reconcile-paper (22:30 / 23:45 UTC)
  Trading    shadow-paper recon 00:15 UTC

Watch:
  tail -f /var/log/hibs-bet/hands-off-cycle.log
  tail -f /var/log/hibs-bet/prediction-results-all.log
  tail -f /var/log/hibs-racing/robust-racing-scrape.log
  cat /var/log/hibs-bet/data-producer-slo.json

Crons:
  crontab -u www-data -l | grep -E 'hibs|trading'

Re-arm after code changes:
  sudo bash ${RACING}/deploy/vps-autonomous-install.sh
EOF

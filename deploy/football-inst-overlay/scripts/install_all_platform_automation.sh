#!/usr/bin/env bash
# ONE COMMAND — automate all four pill-switcher platforms on consolidated VPS.
#
# Football · Racing · Trading · Lines (FVE)
# Arms crons, hands-off repair (30m), fixture warm, evidence seed, engineering controls.
#
# On VPS as root (after code is in /opt/hibs-bet):
#   sudo bash /opt/hibs-bet/scripts/install_all_platform_automation.sh
#
# Sync latest automation branch first (if scripts missing):
#   sudo HIBS_SYNC_REF=cursor/full-platform-automation-7e4d \
#     bash /opt/hibs-bet/deploy/vps-sync-from-github.sh
#   sudo bash /opt/hibs-bet/scripts/install_all_platform_automation.sh
#
# From Mac:
#   DEPLOY_HOST=87.106.100.52 ./scripts/install_all_platform_automation.sh --remote
#
# Options:
#   --sync-only     gitHub archive sync then exit
#   --skip-sync     do not run vps-sync-from-github
#   --new-evidence-date  reset HIBS_EVIDENCE_DEPLOY_DATE
set -euo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
TRADING="${TRADING_INSTALL_ROOT:-/opt/trading-core}"
PUBLIC="${HIBS_PUBLIC_HOST:-hibs-bet.co.uk}"
VPS_IP="${HIBS_VPS_IP:-87.106.100.52}"
SYNC_REF="${HIBS_SYNC_REF:-cursor/robust-scrape-inst-7e4d}"
REMOTE=0
SKIP_SYNC=0
SYNC_ONLY=0
NEW_DATE=0
EXTRA_ARGS=()

for arg in "$@"; do
  case "${arg}" in
    --remote) REMOTE=1 ;;
    --skip-sync) SKIP_SYNC=1 ;;
    --sync-only) SYNC_ONLY=1 ;;
    --new-evidence-date) NEW_DATE=1; EXTRA_ARGS+=(--new-evidence-date) ;;
  esac
done

if [[ "${REMOTE}" -eq 1 ]]; then
  HOST="${DEPLOY_HOST:-${VPS_IP}}"
  USER="${DEPLOY_USER:-root}"
  flags=""
  [[ "${SKIP_SYNC}" -eq 1 ]] && flags="${flags} --skip-sync"
  [[ "${SYNC_ONLY}" -eq 1 ]] && flags="${flags} --sync-only"
  [[ "${NEW_DATE}" -eq 1 ]] && flags="${flags} --new-evidence-date"
  exec ssh -o BatchMode=yes -o ConnectTimeout=30 "${USER}@${HOST}" \
    "export DEPLOY_PATH='${APP}' HIBS_RACING_DEPLOY_PATH='${RACING}' TRADING_INSTALL_ROOT='${TRADING}' \
     HIBS_PUBLIC_HOST='${PUBLIC}' HIBS_VPS_IP='${VPS_IP}' HIBS_SYNC_REF='${SYNC_REF}'; \
     bash '${APP}/scripts/install_all_platform_automation.sh' ${flags}"
fi

step() { echo ""; echo "========== $* =========="; }
warn() { echo "[automate-all] WARN: $*" >&2; }

[[ "$(id -u)" -eq 0 ]] || { echo "run as root on VPS: sudo bash $0" >&2; exit 1; }

step "0) Log dir + stack.env"
mkdir -p /var/log/hibs-bet /var/log/hibs-racing /var/run/hibs-bet /etc/hibs-bet
cat >/etc/hibs-bet/stack.env <<EOF
FVE_REMOTE_HOST=127.0.0.1
HIBS_PUBLIC_HOST=${PUBLIC}
HIBS_VPS_IP=${VPS_IP}
EOF

if [[ "${SKIP_SYNC}" -eq 0 && -f "${APP}/deploy/vps-sync-from-github.sh" ]]; then
  step "1) Sync code from GitHub (${SYNC_REF})"
  HIBS_SYNC_REF="${SYNC_REF}" APP_ROOT="${APP}" \
    bash "${APP}/deploy/vps-sync-from-github.sh" || warn "github sync failed — continuing with on-disk tree"
fi

if [[ "${SYNC_ONLY}" -eq 1 ]]; then
  echo "Sync complete (--sync-only)."
  exit 0
fi

[[ -d "${APP}/deploy" ]] || {
  echo "ERROR: ${APP}/deploy missing — run with sync or clone hibs-bet first." >&2
  exit 1
}

if [[ ! -f "${APP}/scripts/install_four_stack_automation.sh" ]]; then
  warn "install_four_stack_automation.sh missing — try: HIBS_SYNC_REF=${SYNC_REF} vps-sync-from-github.sh"
  exit 1
fi

step "2) www-data cron sudoers (hands-off repair)"
if [[ -f "${APP}/deploy/install-hibs-cron-sudoers.sh" ]]; then
  bash "${APP}/deploy/install-hibs-cron-sudoers.sh"
fi

step "3) Engineering grade A + trial production profile"
if [[ -f "${APP}/deploy/apply-vps-engineering-grade-a.sh" ]]; then
  bash "${APP}/deploy/apply-vps-engineering-grade-a.sh" "${EXTRA_ARGS[@]}"
elif [[ -f "${APP}/deploy/apply-vps-trial-production.sh" ]]; then
  bash "${APP}/deploy/apply-vps-safe-production.sh" 2>/dev/null || true
  bash "${APP}/deploy/apply-vps-trial-production.sh"
  bash "${APP}/deploy/apply-vps-domestic-evidence.sh" "${EXTRA_ARGS[@]}" 2>/dev/null || true
  bash "${APP}/deploy/cron-hibs-ops-automation.sh" --install
  bash "${APP}/scripts/install_hands_off_automation.sh"
else
  warn "no engineering/trial apply scripts — arming hands-off only"
  bash "${APP}/scripts/install_hands_off_automation.sh"
fi

step "4) Four-stack automation (racing + trading + FVE + crons)"
export DEPLOY_PATH="${APP}" HIBS_RACING_DEPLOY_PATH="${RACING}" TRADING_INSTALL_ROOT="${TRADING}"
HIBS_VPS_IP="${VPS_IP}" HIBS_PUBLIC_HOST="${PUBLIC}" \
  bash "${APP}/scripts/install_four_stack_automation.sh" --skip-sync

step "5) Immediate football fixture warm (unblocks empty dashboard)"
if [[ -f "${APP}/deploy/cron-hibs-football-fixture-warm.sh" ]]; then
  bash "${APP}/deploy/cron-hibs-football-fixture-warm.sh" --install
  HIBS_FIXTURE_WARM_FORCE_REFRESH=1 HOME="${APP}" DEPLOY_PATH="${APP}" \
    bash "${APP}/scripts/warm_football_fixtures.sh" \
    >>/var/log/hibs-bet/fixture-warm.log 2>&1 || warn "fixture warm failed — check FOOTBALL_DATA_ORG_KEY / scrapers in .env"
fi

step "5b) Low-source scrape automation (FDO/FotMob/ESPN — no API-Sports)"
if [[ -f "${APP}/deploy/cron-hibs-low-source-scrape.sh" ]]; then
  bash "${APP}/deploy/cron-hibs-low-source-scrape.sh" --install
  HOME="${APP}" DEPLOY_PATH="${APP}" bash "${APP}/scripts/warm_low_source_scrape.sh" \
    >>/var/log/hibs-bet/low-source-scrape.log 2>&1 || warn "low-source scrape failed — check scraper flags in .env"
fi

step "5c) Racing robust scrape + cross-platform prediction results"
if [[ -f "${RACING}/deploy/cron-hibs-racing-scrape.sh" ]]; then
  bash "${RACING}/deploy/cron-hibs-racing-scrape.sh" --install
  HOME="${RACING}" bash "${RACING}/scripts/warm_racing_scrape.sh" \
    >>/var/log/hibs-racing/robust-racing-scrape.log 2>&1 || warn "racing scrape warm failed"
fi
PRED_CRON="${APP}/deploy/cron-hibs-prediction-results-all.sh"
[[ -f "${PRED_CRON}" ]] || PRED_CRON="${RACING}/deploy/cron-hibs-prediction-results-all.sh"
if [[ -f "${PRED_CRON}" ]]; then
  bash "${PRED_CRON}" --install
  bash "${PRED_CRON}" --run >>/var/log/hibs-bet/prediction-results-all.log 2>&1 || warn "prediction results run failed"
fi

step "5d) Racing cards (service + daily refresh)"
if [[ -d "${RACING}" && -f "${APP}/scripts/vps_racing_repair.sh" ]]; then
  bash "${APP}/scripts/vps_racing_repair.sh" \
    >>/var/log/hibs-racing/daily-refresh.log 2>&1 || warn "racing repair failed — check raceform.db + Racing API keys"
fi

step "6) Data producer repair (football bundle + FVE + racing)"
if [[ -f "${APP}/scripts/data_producer_repair.sh" ]]; then
  bash "${APP}/scripts/data_producer_repair.sh" || warn "data producer still red"
fi

step "7) Hands-off cycle now (don't wait 30m)"
bash "${APP}/scripts/hands_off_cycle.sh" || true

step "8) Status"
if [[ -f "${APP}/scripts/verify_inst_pp_automation.sh" ]]; then
  bash "${APP}/scripts/verify_inst_pp_automation.sh" || true
fi
if [[ -f "${APP}/scripts/verify_engineering_grade_a.sh" ]]; then
  bash "${APP}/scripts/verify_engineering_grade_a.sh" || true
fi

cat <<EOF

========== ALL-PLATFORM AUTOMATION ARMED ==========

Products (auto-repair every 30m + fixture warm every 3h):

  Football   https://${PUBLIC}/
  Racing     https://${PUBLIC}/racing/
  Trading    https://${PUBLIC}/harvested-execution
  Lines      https://${PUBLIC}/line-trader

Watch logs:
  tail -f /var/log/hibs-bet/hands-off-cycle.log
  tail -f /var/log/hibs-bet/fixture-warm.log
  tail -f /var/log/hibs-bet/low-source-scrape.log
  cat /var/log/hibs-bet/data-producer-slo.json

Crons:
  crontab -u www-data -l | grep hibs

If football still empty — set in ${APP}/.env then re-run step 5:
  FOOTBALL_DATA_ORG_KEY=<your key>
  # or disable scrape-only: HIBS_DISABLE_API_SPORTS=0 + API_FOOTBALL_KEY

Re-arm anytime:
  sudo bash ${APP}/scripts/install_all_platform_automation.sh --skip-sync
EOF

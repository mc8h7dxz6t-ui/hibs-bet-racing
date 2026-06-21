#!/usr/bin/env bash
# Arm hands-off automation using ONLY /opt/hibs-bet (no hibs-bet-racing git sync).
# Use when private GitHub blocks clone and football/racing services already run.
#
#   sudo bash /opt/hibs-bet/deploy/vps-arm-hands-off-no-racing-sync.sh
set -euo pipefail

BET="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
TRADING="${TRADING_INSTALL_ROOT:-/opt/trading-core}"

[[ "$(id -u)" -eq 0 ]] || { echo "run as root" >&2; exit 1; }
[[ -d "${BET}/src" ]] || { echo "missing ${BET}" >&2; exit 1; }

step() { echo ""; echo "========== $* =========="; }

step "1) Scrape-first profile (if script present)"
[[ -f "${BET}/deploy/apply-vps-scrape-first-institutional.sh" ]] && \
  bash "${BET}/deploy/apply-vps-scrape-first-institutional.sh" || \
  [[ -f "${BET}/deploy/apply-vps-scrape-first.sh" ]] && \
  bash "${BET}/deploy/apply-vps-scrape-first.sh" || true

step "2) Prediction logging env"
touch "${BET}/.env"
for kv in \
  HIBS_PRODUCTION=1 \
  HIBS_PREDICTION_LOG_ENABLED=1 \
  HIBS_CLV_LOG_ENABLED=1 \
  HIBS_FOOTBALL_DATA_AUTO_SKIP_PAID=1 \
  HIBS_FOOTBALL_DATA_SKIP_COMPS=CL,EL,UECL,WC,SA,FL1,BL1,PD,CDR,DFB \
  HIBS_HEALTH_RACING_PROBE=1 \
  HIBS_RACING_EVIDENCE_LOCAL=1; do
  k="${kv%%=*}"
  grep -q "^${k}=" "${BET}/.env" 2>/dev/null || echo "${kv}" >>"${BET}/.env"
done
chown www-data:www-data "${BET}/.env"

step "3) Crons"
[[ -f "${BET}/deploy/install-hibs-cron-sudoers.sh" ]] && bash "${BET}/deploy/install-hibs-cron-sudoers.sh"
[[ -f "${BET}/scripts/install_hands_off_automation.sh" ]] && bash "${BET}/scripts/install_hands_off_automation.sh"
[[ -f "${BET}/deploy/cron-hibs-low-source-scrape.sh" ]] && bash "${BET}/deploy/cron-hibs-low-source-scrape.sh" --install || true

step "4) Racing env (on-disk tree)"
if [[ -d "${RACING}" ]]; then
  touch "${RACING}/.env"
  grep -q '^HIBS_ODDS_SOURCE=' "${RACING}/.env" 2>/dev/null || echo 'HIBS_ODDS_SOURCE=auto' >>"${RACING}/.env"
  chown www-data:www-data "${RACING}/.env" 2>/dev/null || true
  systemctl restart hibs-racing 2>/dev/null || true
fi

step "5) Warm + hands-off cycle"
[[ -f "${BET}/scripts/warm_low_source_scrape.sh" ]] && \
  HOME="${BET}" bash "${BET}/scripts/warm_low_source_scrape.sh" || \
  [[ -f "${BET}/scripts/warm_football_fixtures.sh" ]] && \
  HIBS_FIXTURE_WARM_FORCE_REFRESH=1 HOME="${BET}" bash "${BET}/scripts/warm_football_fixtures.sh" || true
[[ -f "${BET}/scripts/hands_off_cycle.sh" ]] && bash "${BET}/scripts/hands_off_cycle.sh" || true

step "6) Ping"
curl -sS --max-time 8 http://127.0.0.1:8000/api/ping | head -c 200 || true
echo ""
curl -sS --max-time 8 http://127.0.0.1:5003/api/ping | head -c 200 || true
echo ""

cat <<EOF

========== HANDS-OFF ARMED (no racing git sync) ==========
Crons: crontab -u www-data -l | grep hibs

For full Inst++ deploy scripts later, add GitHub token then:
  sudo mkdir -p /etc/hibs-bet/secrets
  sudo bash -c 'echo YOUR_GITHUB_PAT > /etc/hibs-bet/secrets/racing_github_token'
  sudo chmod 600 /etc/hibs-bet/secrets/racing_github_token
  sudo HIBS_RACING_SYNC_REF=cursor/robust-scrape-inst-7e4d \\
    bash ${BET}/deploy/vps-sync-racing-from-github.sh
EOF

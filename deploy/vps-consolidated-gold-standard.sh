#!/usr/bin/env bash
# Consolidated VPS (87.106.100.52) — one-shot gold-standard hands-off automation.
#
# Football + Racing autonomous on www.hibs-bet.co.uk; trading parked after Day-15 FAIL.
#
#   sudo bash /opt/hibs-bet/deploy/vps-consolidated-gold-standard.sh
#
# Re-run safely after code sync — idempotent.
set -euo pipefail

BET="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
TRADING="${TRADING_INSTALL_ROOT:-/opt/trading-core}"
PUBLIC="${HIBS_PUBLIC_HOST:-hibs-bet.co.uk}"
VPS_IP="${HIBS_VPS_IP:-87.106.100.52}"

step() { echo ""; echo "========== $* =========="; }
warn() { echo "[gold-standard] WARN: $*" >&2; }

[[ "$(id -u)" -eq 0 ]] || { echo "run as root: sudo bash $0" >&2; exit 1; }
[[ -d "${BET}/deploy" ]] || { echo "missing ${BET}" >&2; exit 1; }

step "1) Consolidated stack identity (no legacy .73 SSH)"
mkdir -p /etc/hibs-bet /var/log/hibs-bet /var/log/hibs-racing
cat >/etc/hibs-bet/stack.env <<EOF
FVE_REMOTE_HOST=127.0.0.1
HIBS_PUBLIC_HOST=${PUBLIC}
HIBS_VPS_IP=${VPS_IP}
HIBS_TRADING_SHADOW_HARD_STOP=1
EOF

touch "${BET}/.env"
for kv in \
  HIBS_PRODUCTION=1 \
  HIBS_PREDICTION_LOG_ENABLED=1 \
  HIBS_CLV_LOG_ENABLED=1 \
  HIBS_PREDICTION_LOG_ALWAYS=1 \
  HIBS_HEALTH_RACING_PROBE=1 \
  HIBS_RACING_EVIDENCE_LOCAL=1 \
  HIBS_AUTH_PUBLIC_HEALTH=1 \
  HIBS_TRADING_SHADOW_HARD_STOP=1; do
  k="${kv%%=*}"
  grep -q "^${k}=" "${BET}/.env" 2>/dev/null || echo "${kv}" >>"${BET}/.env"
done
# Enforce hard stop even if already set off
if grep -q '^HIBS_TRADING_SHADOW_HARD_STOP=' "${BET}/.env" 2>/dev/null; then
  sed -i 's/^HIBS_TRADING_SHADOW_HARD_STOP=.*/HIBS_TRADING_SHADOW_HARD_STOP=1/' "${BET}/.env"
else
  echo 'HIBS_TRADING_SHADOW_HARD_STOP=1' >>"${BET}/.env"
fi
chown www-data:www-data "${BET}/.env" 2>/dev/null || true

step "2) Trading parked (Day-15 FAIL — do not auto-restart soak)"
systemctl stop trading-shadow-soak 2>/dev/null || true
systemctl disable trading-shadow-soak 2>/dev/null || true
echo "trading-shadow-soak: $(systemctl is-active trading-shadow-soak 2>/dev/null || echo inactive)"

step "3) Scrape-first football profile + fixture cache"
[[ -f "${BET}/deploy/apply-vps-scrape-first-institutional.sh" ]] && \
  bash "${BET}/deploy/apply-vps-scrape-first-institutional.sh"
if [[ -f "${BET}/scripts/lib_scrape_first_cache.sh" ]]; then
  # shellcheck source=lib_scrape_first_cache.sh
  source "${BET}/scripts/lib_scrape_first_cache.sh"
  scrape_first_cache_warm || warn "scrape-first cache warm incomplete"
fi
[[ -f "${BET}/scripts/vps_fixture_repair.sh" ]] && \
  bash "${BET}/scripts/vps_fixture_repair.sh" || warn "fixture repair issues"

step "4) nginx — www feeds football :8000 + racing :5003"
cp "${BET}/deploy/hibs-bet.nginx.conf" /etc/nginx/sites-available/hibs-bet
ln -sf /etc/nginx/sites-available/hibs-bet /etc/nginx/sites-enabled/hibs-bet
rm -f /etc/nginx/sites-enabled/default
[[ -f "${BET}/deploy/apply-vps-racing-link.sh" ]] && \
  DEPLOY_PATH="${BET}" HIBS_RACING_DEPLOY_PATH="${RACING}" bash "${BET}/deploy/apply-vps-racing-link.sh"
[[ -f "${BET}/deploy/apply-vps-site-cross-links.sh" ]] && \
  DEPLOY_PATH="${BET}" bash "${BET}/deploy/apply-vps-site-cross-links.sh"
nginx -t && systemctl reload nginx

step "5) Arm all crons (hands-off 30m + audits + racing + prediction results)"
[[ -f "${BET}/deploy/install-hibs-cron-sudoers.sh" ]] && bash "${BET}/deploy/install-hibs-cron-sudoers.sh"
[[ -f "${BET}/scripts/install_hands_off_automation.sh" ]] && \
  DEPLOY_PATH="${BET}" HIBS_RACING_DEPLOY_PATH="${RACING}" bash "${BET}/scripts/install_hands_off_automation.sh"
[[ -f "${BET}/deploy/cron-hibs-low-source-scrape.sh" ]] && bash "${BET}/deploy/cron-hibs-low-source-scrape.sh" --install
PRED="${BET}/deploy/cron-hibs-prediction-results-all.sh"
[[ -f "${PRED}" ]] || PRED="${RACING}/deploy/cron-hibs-prediction-results-all.sh"
[[ -f "${PRED}" ]] && bash "${PRED}" --install
[[ -f "${RACING}/deploy/cron-hibs-racing-scrape.sh" ]] && bash "${RACING}/deploy/cron-hibs-racing-scrape.sh" --install

step "6) Stack wiring + FVE local"
[[ -f "${BET}/deploy/ensure-vps-stack-wiring.sh" ]] && \
  bash "${BET}/deploy/ensure-vps-stack-wiring.sh" --repair || true
[[ -f "${BET}/deploy/apply-vps-fve-line-trader.sh" ]] && \
  HIBS_PUBLIC_HOST="${PUBLIC}" bash "${BET}/deploy/apply-vps-fve-line-trader.sh" || true

step "7) Initial repair cycle"
[[ -f "${BET}/scripts/hands_off_cycle.sh" ]] && bash "${BET}/scripts/hands_off_cycle.sh" || true
[[ -f "${BET}/scripts/vps_three_stack_green.sh" ]] && bash "${BET}/scripts/vps_three_stack_green.sh" --repair || true

step "8) Public + local verify"
PY="${BET}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY=python3
echo "--- localhost ---"
curl -sS --max-time 15 http://127.0.0.1:8000/api/ping | head -c 200 || echo "football ping FAIL"
echo ""
curl -sS --max-time 8 http://127.0.0.1:5003/api/ping | head -c 200 || echo "racing ping FAIL"
echo ""
echo "--- public www ---"
curl -sS --max-time 20 "https://${PUBLIC}/api/ping" | head -c 200 || echo "public football FAIL"
echo ""
curl -sS --max-time 10 "https://${PUBLIC}/racing/api/ping" | head -c 200 || echo "public racing FAIL"
echo ""

cat <<EOF

========== GOLD STANDARD HANDS-OFF ARMED ==========

Autonomous loops (no daily SSH):
  */30  hands-off cycle (repair + scrape + evidence)
  */2h  low-source football scrape
  3x/d  racing card refresh
  daily prediction results (football + racing + trading recon read-only)

Trading: PARKED (HIBS_TRADING_SHADOW_HARD_STOP=1)

Watch:
  tail -f /var/log/hibs-bet/hands-off-cycle.log
  cat /var/log/hibs-bet/three-stack-status.json
  cat /var/log/hibs-bet/hands-off-status.json

Re-arm after git sync:
  sudo bash ${BET}/deploy/vps-consolidated-gold-standard.sh
EOF

#!/usr/bin/env bash
# Apply football Inst++ overlay onto /opt/hibs-bet (preserves .env, data, .venv).
#
# Overlay ships in hibs-bet-racing at deploy/football-inst-overlay/ when hibs-bet.git
# branch push is blocked.
#
#   sudo bash /opt/hibs-racing/deploy/vps-sync-football-inst-overlay.sh
#   sudo OVERLAY_ROOT=/opt/hibs-bet/deploy/football-inst-overlay bash ...
set -euo pipefail

BET="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
OVERLAY="${OVERLAY_ROOT:-${RACING}/deploy/football-inst-overlay}"
DOMAIN="${HIBS_DOMAIN:-hibs-bet.co.uk}"
HOST="${DEPLOY_HOST:-$(hostname -s 2>/dev/null || hostname -f 2>/dev/null || echo vps)}"
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
REF="${HIBS_OVERLAY_REVISION:-main@football-inst-overlay}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

[[ -d "${OVERLAY}" ]] || {
  echo "ERROR: overlay missing at ${OVERLAY}" >&2
  echo "Sync hibs-bet-racing branch cursor/robust-scrape-inst-7e4d first." >&2
  exit 1
}
[[ -d "${BET}" ]] || {
  echo "ERROR: football root missing at ${BET}" >&2
  exit 1
}

echo "==> rsync overlay ${OVERLAY}/ -> ${BET}/"
rsync -a \
  --exclude 'OVERLAY_REVISION' \
  --exclude '.env' \
  --exclude '.venv/' \
  --exclude '.cache/' \
  --exclude 'data/prediction_audit.sqlite' \
  --exclude 'data/prediction_audit_vps.sqlite' \
  "${OVERLAY}/" "${BET}/"

chmod +x "${BET}/scripts/"*.sh "${BET}/deploy/"*.sh 2>/dev/null || true
mkdir -p "${BET}/.cache" "${BET}/logs" "${BET}/data"
chown -R www-data:www-data "${BET}/src" "${BET}/scripts" "${BET}/deploy" "${BET}/.cache" "${BET}/logs" "${BET}/data" 2>/dev/null || true
chmod 775 "${BET}/.cache" "${BET}/logs" 2>/dev/null || true

if [[ -f "${BET}/requirements.txt" && -x "${BET}/.venv/bin/pip" ]]; then
  echo "==> pip install (deps refresh)"
  find "${BET}/.venv/lib" -type d -name '~*' -prune -exec rm -rf {} + 2>/dev/null || true
  sudo -u www-data "${BET}/.venv/bin/pip" install -q -r "${BET}/requirements.txt" 2>/dev/null || true
fi

if [[ -f "${BET}/.football-overlay-revision" ]]; then
  cat "${BET}/.football-overlay-revision"
fi

if [[ -f "${BET}/scripts/evaluate_trading_day15_gate.py" && -d "${TRADING_INSTALL_ROOT:-/opt/trading-core}/scripts" ]]; then
  echo "==> sync Day-15 gate -> trading-core"
  TRADING_INSTALL_ROOT="${TRADING_INSTALL_ROOT:-/opt/trading-core}" \
    bash "${BET}/deploy/sync-trading-day15-gate.sh" 2>/dev/null || \
    rsync -a "${BET}/scripts/evaluate_trading_day15_gate.py" \
      "${TRADING_INSTALL_ROOT:-/opt/trading-core}/scripts/evaluate_trading_day15_gate.py"
fi

if [[ -f "${BET}/deploy/hibs-bet.service" ]]; then
  echo "==> install hibs-bet.service"
  cp "${BET}/deploy/hibs-bet.service" /etc/systemd/system/hibs-bet.service
  systemctl daemon-reload
fi

cat >"${BET}/.deploy-revision" <<EOF
revision=${REF}
deployed_at=${STAMP}
deploy_host=${HOST}
domain=${DOMAIN}
service=hibs-bet
sync_source=football_inst_overlay
EOF
chown www-data:www-data "${BET}/.deploy-revision"

if systemctl is-enabled hibs-bet &>/dev/null; then
  echo "==> restart hibs-bet"
  systemctl restart hibs-bet.service
  sleep 4
  if systemctl is-active hibs-bet.service; then
    echo "OK: hibs-bet active"
  else
    echo "WARN: hibs-bet not active — run: sudo bash ${BET}/scripts/vps_football_hard_recovery.sh" >&2
  fi
else
  echo "WARN: hibs-bet service not enabled — start manually: systemctl enable --now hibs-bet"
fi

if [[ -f "${BET}/deploy/cron-hibs-infra-fallback.sh" ]]; then
  echo "==> install 5m infra fallback cron (idempotent)"
  bash "${BET}/deploy/cron-hibs-infra-fallback.sh" --install 2>/dev/null || true
fi

if [[ "${HIBS_OVERLAY_SKIP_WARM:-0}" != "1" ]]; then
  echo "==> post-sync fixture warm (set HIBS_OVERLAY_SKIP_WARM=1 to skip)"
  if [[ -f "${BET}/scripts/warm_low_source_scrape.sh" ]]; then
    sudo -u www-data env \
      HOME="${BET}" DEPLOY_PATH="${BET}" PYTHONPATH="${BET}/src" \
      HIBS_LOW_SOURCE_SCRAPE_FORCE=1 \
      bash "${BET}/scripts/warm_low_source_scrape.sh" || echo "WARN: low-source scrape warm failed"
  fi
  if [[ -f "${BET}/scripts/warm_football_fixtures.sh" ]]; then
    FOOTBALL_WARM_FORCE="${HIBS_OVERLAY_FORCE_FIXTURE_WARM:-0}"
    sudo -u www-data env \
      HOME="${BET}" DEPLOY_PATH="${BET}" PYTHONPATH="${BET}/src" \
      HIBS_FIXTURE_WARM_FORCE_REFRESH="${FOOTBALL_WARM_FORCE}" \
      bash "${BET}/scripts/warm_football_fixtures.sh" || echo "WARN: fixture warm failed"
  fi
fi

echo ""
echo "==> verify"
curl -fsS --max-time 10 "http://127.0.0.1:8000/api/ping" 2>/dev/null | head -c 400 || true
echo ""
echo ""
echo "==> football overlay applied to ${BET} at ${STAMP}"

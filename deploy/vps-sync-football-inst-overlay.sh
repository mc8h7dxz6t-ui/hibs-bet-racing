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
chown -R www-data:www-data "${BET}/src" "${BET}/scripts" "${BET}/deploy" 2>/dev/null || true

if [[ -f "${BET}/requirements.txt" && -x "${BET}/.venv/bin/pip" ]]; then
  echo "==> pip install (deps refresh)"
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

echo "==> football overlay applied to ${BET}"

#!/usr/bin/env bash
# Install systemd unit for hibs-racing trading daemon (simulation only).
#
#   sudo bash /opt/hibs-racing/deploy/apply-trading-daemon.sh
#   sudo bash /opt/hibs-racing/deploy/apply-trading-daemon.sh --enable
#
set -euo pipefail

RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
ENABLE=0
[[ "${1:-}" == "--enable" ]] && ENABLE=1

[[ "$(id -u)" -ne 0 ]] && { echo "run as root" >&2; exit 1; }

install -m 0644 "${RACING}/deploy/hibs-trading-daemon.service" /etc/systemd/system/hibs-trading-daemon.service
systemctl daemon-reload

ENV_FILE="${RACING}/.env"
touch "${ENV_FILE}"
upsert() {
  local k="$1" v="$2"
  grep -q "^${k}=" "${ENV_FILE}" && sed -i "s|^${k}=.*|${k}=${v}|" "${ENV_FILE}" || echo "${k}=${v}" >> "${ENV_FILE}"
}
upsert "HIBS_LIVE_TRADING_ENABLED" "false"
upsert "HIBS_LIQUIDITY_ROUTER_ACTIVE" "false"
upsert "HIBS_EXECUTION_LATENCY_MAX_MS" "250"
upsert "HIBS_SLIPPAGE_MAX_TICKS" "2"
upsert "HIBS_FLIGHT_LATENCY_MAX_MS" "450"
upsert "HIBS_ADVERSE_SELECTION_VOLUME_DROP_PCT" "0.40"

if [[ "${ENABLE}" -eq 1 ]]; then
  systemctl enable --now hibs-trading-daemon
  systemctl status hibs-trading-daemon --no-pager || true
else
  echo "Installed unit. Start with: sudo systemctl enable --now hibs-trading-daemon"
fi

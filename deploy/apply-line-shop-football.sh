#!/usr/bin/env bash
# Line Shop env upsert for hibs-bet. File copy is legacy — Line Shop ships in hibs-bet git (Phase 1).
#
#   sudo bash /opt/hibs-racing/deploy/apply-line-shop-football.sh
#   sudo HIBS_LINE_SHOP_COPY_OVERLAY=1 bash ...   # force overlay file copy (legacy VPS only)
#
set -euo pipefail

RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
BET="${HIBS_BET_DEPLOY_PATH:-/opt/hibs-bet}"
OVERLAY="${RACING}/deploy/football-inst-overlay"
COPY_OVERLAY="${HIBS_LINE_SHOP_COPY_OVERLAY:-0}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

[[ -d "${BET}/templates" ]] || { echo "missing ${BET}/templates — sync hibs-bet first" >&2; exit 1; }

if [[ "${COPY_OVERLAY}" == "1" ]]; then
  [[ -d "${OVERLAY}/templates" ]] || { echo "missing overlay at ${OVERLAY}" >&2; exit 1; }
  copy_one() {
    local rel="$1"
    local src="${OVERLAY}/${rel}"
    local dest="${BET}/${rel}"
    [[ -f "${src}" ]] || { echo "WARN: skip missing ${rel}" >&2; return 0; }
    mkdir -p "$(dirname "${dest}")"
    install -m 0644 "${src}" "${dest}"
    echo "==> ${rel}"
  }
  echo "==> Line Shop overlay copy (legacy) ${OVERLAY} -> ${BET}"
  copy_one "templates/line_trader.html"
  copy_one "static/line_trader_shop.js"
  copy_one "static/fve_ws_lines.js"
  copy_one "src/hibs_predictor/fve_status.py"
  copy_one "src/hibs_predictor/web.py"
  chown -R www-data:www-data \
    "${BET}/templates/line_trader.html" \
    "${BET}/static/line_trader_shop.js" \
    "${BET}/static/fve_ws_lines.js" \
    "${BET}/src/hibs_predictor/fve_status.py" \
    "${BET}/src/hibs_predictor/web.py" 2>/dev/null || true
else
  if [[ -f "${BET}/static/line_trader_shop.js" ]]; then
    echo "==> Line Shop git canonical — skipping overlay file copy (set HIBS_LINE_SHOP_COPY_OVERLAY=1 to override)"
  else
    echo "WARN: ${BET}/static/line_trader_shop.js missing — sync hibs-bet git or set HIBS_LINE_SHOP_COPY_OVERLAY=1" >&2
  fi
fi

ENV_FILE="${BET}/.env"
touch "${ENV_FILE}"
upsert() {
  local key="$1" val="$2"
  if grep -q "^${key}=" "${ENV_FILE}" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" "${ENV_FILE}"
  else
    echo "${key}=${val}" >> "${ENV_FILE}"
  fi
}

echo "==> upsert FVE / Line Shop env keys in ${ENV_FILE}"
upsert "HIBS_FVE_INTEGRATION" "1"
upsert "HIBS_LINE_TRADER_URL" "/line-trader"
upsert "HIBS_FVE_DECAY_TIMEOUT_SECS" "120"
upsert "HIBS_FVE_ARB_DELTA_BPS" "50"
upsert "HIBS_FVE_STATUS_TTL_SEC" "12"
upsert "HIBS_FVE_FORCE_PAUSED" "0"
if ! grep -q '^FVE_API_URL=' "${ENV_FILE}" 2>/dev/null; then
  upsert "FVE_API_URL" "http://127.0.0.1:8010"
fi
if ! grep -q '^HIBS_FVE_PUBLIC_API_URL=' "${ENV_FILE}" 2>/dev/null; then
  upsert "HIBS_FVE_PUBLIC_API_URL" "https://hibs-bet.co.uk/fve-api"
  upsert "HIBS_FVE_PUBLIC_WS_URL" "wss://hibs-bet.co.uk/fve-api"
fi

echo "==> restart hibs-bet"
systemctl restart hibs-bet
sleep 5
curl -sS -o /dev/null -w 'ping=%{http_code}\n' http://127.0.0.1:8000/api/ping || true
echo "==> done — verify /line-trader in browser (Line Shop matrix)"

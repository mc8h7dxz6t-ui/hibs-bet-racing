#!/usr/bin/env bash
# Main hibs-bet VPS: point FVE + nginx /fve-api at a remote FVE host (dedicated 1GB box).
#
# Prereqs: bootstrap-fve-dedicated-1gb.sh already ran on the FVE VPS.
#
# On hibs-bet-vps (77.68.89.73):
#   sudo FVE_REMOTE_HOST=77.68.89.75 bash /opt/hibs-bet/deploy/apply-vps-fve-remote-host.sh
set -euo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
FVE_REMOTE_HOST="${FVE_REMOTE_HOST:-}"
FVE_PORT="${FVE_API_PORT:-8010}"
PUBLIC_HOST="${HIBS_PUBLIC_HOST:-hibs-bet.co.uk}"

log() { echo "[fve-remote] $*"; }

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo FVE_REMOTE_HOST=... bash $0" >&2
  exit 1
fi

if [[ -z "${FVE_REMOTE_HOST}" ]]; then
  echo "Set FVE_REMOTE_HOST (e.g. 77.68.89.75)" >&2
  exit 1
fi

FVE_UPSTREAM="http://${FVE_REMOTE_HOST}:${FVE_PORT}"

log "1/5 — hibs FVE upstream proxy (/api/fve/lines)"
bash "${APP}/deploy/vps-install-fve-upstream.sh"

log "2/5 — hibs .env remote FVE"
touch "${APP}/.env"
upsert() {
  local key="$1" val="$2"
  if grep -q "^${key}=" "${APP}/.env" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" "${APP}/.env"
  else
    echo "${key}=${val}" >> "${APP}/.env"
  fi
}
upsert HIBS_FVE_INTEGRATION 1
upsert FVE_API_URL "${FVE_UPSTREAM}"
upsert HIBS_FVE_PUBLIC_API_URL "https://${PUBLIC_HOST}/fve-api"
upsert HIBS_FVE_PUBLIC_WS_URL "wss://${PUBLIC_HOST}/fve-api"
upsert HIBS_LINE_TRADER_URL "/line-trader"

log "3/5 — nginx /fve-api → ${FVE_UPSTREAM}"
FVE_UPSTREAM_HOST="${FVE_REMOTE_HOST}" FVE_API_PORT="${FVE_PORT}" DEPLOY_PATH="${APP}" \
  HIBS_PUBLIC_HOST="${PUBLIC_HOST}" bash "${APP}/deploy/apply-nginx-fve-line-trader.sh"

log "4/5 — probe remote FVE"
if curl -fsS --max-time 8 "${FVE_UPSTREAM}/health" >/dev/null 2>&1; then
  log "remote /health OK"
else
  log "WARN cannot reach ${FVE_UPSTREAM}/health — check ufw on FVE host allows this server's IP"
fi

log "5/5 — restart hibs-bet"
systemctl restart hibs-bet 2>/dev/null || true
sleep 3

if curl -fsS --max-time 12 "http://127.0.0.1:8000/api/fve/status" >/dev/null 2>&1; then
  log "/api/fve/status OK"
else
  log "WARN /api/fve/status failed — journalctl -u hibs-bet -n 30"
fi

log "verify:"
echo "  curl -sS http://127.0.0.1:8000/api/fve/status?full=1 | python3 -m json.tool | head -20"
echo "  curl -sS https://${PUBLIC_HOST}/fve-api/health | head -c 300"
echo "  open https://${PUBLIC_HOST}/line-trader"

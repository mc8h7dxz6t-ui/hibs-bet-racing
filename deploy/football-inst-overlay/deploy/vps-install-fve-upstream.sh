#!/usr/bin/env bash
# VPS: wire hibs-bet /api/fve/lines for FVE upstream (no duplicate book ingest).
#
#   sudo bash /opt/hibs-bet/deploy/vps-install-fve-upstream.sh
set -euo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
log() { echo "[hibs-fve-lines] $*"; }

[[ -d "${APP}/src/hibs_predictor" ]] || { echo "ERROR: ${APP} not found" >&2; exit 1; }

if [[ -x "${APP}/scripts/vps_ensure_hibs_bet_venv.sh" ]]; then
  bash "${APP}/scripts/vps_ensure_hibs_bet_venv.sh"
fi

touch "${APP}/.env"
if ! grep -q '^FVE_LINES_TOKEN=' "${APP}/.env" 2>/dev/null; then
  echo "# Optional shared secret for FVE upstream" >> "${APP}/.env"
  echo "FVE_LINES_TOKEN=" >> "${APP}/.env"
fi
if ! grep -q '^HIBS_FVE_INTEGRATION=' "${APP}/.env" 2>/dev/null; then
  echo "HIBS_FVE_INTEGRATION=1" >> "${APP}/.env"
fi
if ! grep -q '^FVE_API_URL=' "${APP}/.env" 2>/dev/null; then
  echo "FVE_API_URL=http://127.0.0.1:8010" >> "${APP}/.env"
fi

systemctl restart hibs-bet 2>/dev/null || true
sleep 2
if curl -fsS --max-time 8 "http://127.0.0.1:8000/api/ping" >/dev/null 2>&1; then
  log "hibs-bet ping OK"
else
  log "WARN hibs-bet ping failed — journalctl -u hibs-bet -n 20"
fi

log "done — FVE .env should use:"
echo "  FVE_UPSTREAM_MODE=hibs"
echo "  HIBS_UPSTREAM_BASE_URL=https://hibs-bet.co.uk"
echo "  HIBS_UPSTREAM_TOKEN=<same as FVE_LINES_TOKEN if set>"

#!/usr/bin/env bash
# Bump UI cache-bust version and restart hibs-racing after theme sync.
#
# Full cross-stack sync (CSS from football → racing) lives in hibs-bet:
#   sudo bash /opt/hibs-bet/deploy/apply-vps-unified-ui-theme.sh
#
# Racing-only refresh (after git pull or manual CSS copy):
#   sudo bash /opt/hibs-racing/deploy/apply-vps-unified-ui-theme.sh
set -euo pipefail

RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
VERSION="$(date -u +%Y%m%d%H%M)"
ENV_FILE="${RACING}/.env"

log() { echo "[racing-unified-ui] $*"; }

[[ "$(id -u)" -eq 0 ]] || { echo "Run as root: sudo bash $0" >&2; exit 1; }
[[ -d "${RACING}" ]] || { echo "Missing ${RACING}" >&2; exit 1; }

touch "${ENV_FILE}"
if grep -q '^HIBS_UI_ASSET_VERSION=' "${ENV_FILE}" 2>/dev/null; then
  sed -i "s/^HIBS_UI_ASSET_VERSION=.*/HIBS_UI_ASSET_VERSION=${VERSION}/" "${ENV_FILE}"
else
  echo "HIBS_UI_ASSET_VERSION=${VERSION}" >> "${ENV_FILE}"
fi
chown www-data:www-data "${ENV_FILE}" 2>/dev/null || true
chmod 640 "${ENV_FILE}" 2>/dev/null || true

find "${RACING}/.cache" -name 'cards*.html' -mmin +120 -delete 2>/dev/null || true

if systemctl is-enabled hibs-racing &>/dev/null; then
  systemctl restart hibs-racing
fi
sleep 2
RC="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 8 http://127.0.0.1:5003/api/ping 2>/dev/null || echo 000)"
log "racing ping=${RC} ui_version=${VERSION}"
echo "Hard refresh: Cmd+Shift+R / Ctrl+Shift+R"

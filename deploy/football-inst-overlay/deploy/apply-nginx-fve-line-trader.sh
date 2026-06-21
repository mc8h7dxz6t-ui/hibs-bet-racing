#!/usr/bin/env bash
# Idempotently add FVE API/WS proxy to nginx (hibs-bet.co.uk → :8010).
#
#   sudo bash /opt/hibs-bet/deploy/apply-nginx-fve-line-trader.sh
set -euo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
FVE_PORT="${FVE_API_PORT:-8010}"
FVE_UPSTREAM_HOST="${FVE_UPSTREAM_HOST:-127.0.0.1}"
SITE_NAME="${NGINX_SITE:-hibs-bet}"
SITE_AVAILABLE="/etc/nginx/sites-available/${SITE_NAME}"
SITE_ENABLED="/etc/nginx/sites-enabled/${SITE_NAME}"
PUBLIC_HOST="${HIBS_PUBLIC_HOST:-hibs-bet.co.uk}"
MARKER_BEGIN="# fve-api proxy begin"
MARKER_END="# fve-api proxy end"

log() { echo "[nginx-fve] $*"; }

if [[ ! -f "${SITE_AVAILABLE}" ]]; then
  if [[ -f "${APP}/deploy/hibs-bet.nginx.conf" ]]; then
    log "installing base site from repo"
    cp "${APP}/deploy/hibs-bet.nginx.conf" "${SITE_AVAILABLE}"
    ln -sf "${SITE_AVAILABLE}" "${SITE_ENABLED}"
  else
    log "ERROR: nginx site ${SITE_AVAILABLE} missing" >&2
    exit 1
  fi
fi

if grep -q "${MARKER_BEGIN}" "${SITE_AVAILABLE}" 2>/dev/null; then
  log "FVE location block present — updating upstream to ${FVE_UPSTREAM_HOST}:${FVE_PORT}"
  sed -i -E "/${MARKER_BEGIN}/,/${MARKER_END}/ s|proxy_pass http://[^;]+;|proxy_pass http://${FVE_UPSTREAM_HOST}:${FVE_PORT}/;|" "${SITE_AVAILABLE}"
else
  log "injecting FVE proxy block into ${SITE_AVAILABLE} → ${FVE_UPSTREAM_HOST}:${FVE_PORT}"
  tmp="$(mktemp)"
  awk -v begin="${MARKER_BEGIN}" -v end="${MARKER_END}" -v port="${FVE_PORT}" -v host="${FVE_UPSTREAM_HOST}" '
    /location \/ \{/ && !done {
      print "    " begin
      print "    location /fve-api/ {"
      print "        proxy_pass http://" host ":" port "/;"
      print "        proxy_http_version 1.1;"
      print "        proxy_set_header Upgrade $http_upgrade;"
      print "        proxy_set_header Connection \"upgrade\";"
      print "        proxy_set_header Host $host;"
      print "        proxy_set_header X-Real-IP $remote_addr;"
      print "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;"
      print "        proxy_set_header X-Forwarded-Proto $scheme;"
      print "        proxy_read_timeout 3600s;"
      print "    }"
      print "    " end
      done=1
    }
    { print }
  ' "${SITE_AVAILABLE}" > "${tmp}"
  mv "${tmp}" "${SITE_AVAILABLE}"
fi

nginx -t
systemctl reload nginx
log "nginx reloaded"

touch "${APP}/.env"
upsert_env() {
  local key="$1" val="$2"
  if grep -q "^${key}=" "${APP}/.env" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" "${APP}/.env"
  else
    echo "${key}=${val}" >> "${APP}/.env"
  fi
}
upsert_env HIBS_FVE_PUBLIC_API_URL "https://${PUBLIC_HOST}/fve-api"
upsert_env HIBS_FVE_PUBLIC_WS_URL "wss://${PUBLIC_HOST}/fve-api"
log "hibs .env public FVE URLs set for ${PUBLIC_HOST}"

#!/usr/bin/env bash
# VPS: nginx /racing + /api/racing → hibs-racing :5003; football upstream :8000.
#
#   sudo DEPLOY_PATH=/opt/hibs-bet bash /opt/hibs-bet/deploy/apply-vps-racing-link.sh
set -euo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
RACING_PORT="${HIBS_RACING_PORT:-5003}"
PUBLIC="${HIBS_PUBLIC_HOST:-hibs-bet.co.uk}"
SITE_NAME="${NGINX_SITE:-hibs-bet}"
SITE_AVAILABLE="/etc/nginx/sites-available/${SITE_NAME}"
SITE_ENABLED="/etc/nginx/sites-enabled/${SITE_NAME}"
MARKER_BEGIN="# hibs-racing proxy begin"
MARKER_END="# hibs-racing proxy end"

log() { echo "[racing-link] $*"; }
warn() { echo "[racing-link] WARN: $*" >&2; }

[[ "$(id -u)" -eq 0 ]] || { echo "run as root: sudo bash $0" >&2; exit 1; }
[[ -d "${APP}/deploy" ]] || { echo "missing ${APP}/deploy" >&2; exit 1; }

if [[ ! -f "${SITE_AVAILABLE}" ]]; then
  if [[ -f "${APP}/deploy/hibs-bet.nginx.conf" ]]; then
    log "installing base nginx site from repo"
    cp "${APP}/deploy/hibs-bet.nginx.conf" "${SITE_AVAILABLE}"
    ln -sf "${SITE_AVAILABLE}" "${SITE_ENABLED}"
  else
    warn "nginx site ${SITE_AVAILABLE} missing and no hibs-bet.nginx.conf in repo"
  fi
fi

if [[ -f "${SITE_AVAILABLE}" ]] && ! grep -q "${MARKER_BEGIN}" "${SITE_AVAILABLE}" 2>/dev/null; then
  if [[ -f "${APP}/deploy/hibs-bet.nginx.conf" ]] && grep -q "${MARKER_BEGIN}" "${APP}/deploy/hibs-bet.nginx.conf"; then
    log "replacing nginx site with canonical hibs-bet.nginx.conf (racing blocks)"
    cp "${APP}/deploy/hibs-bet.nginx.conf" "${SITE_AVAILABLE}"
    ln -sf "${SITE_AVAILABLE}" "${SITE_ENABLED}"
  else
    log "injecting racing proxy block into ${SITE_AVAILABLE}"
    tmp="$(mktemp)"
    awk -v begin="${MARKER_BEGIN}" -v end="${MARKER_END}" -v port="${RACING_PORT}" '
      /location \/ \{/ && !done {
        print "    " begin
        print "    location /racing/ {"
        print "        proxy_pass http://127.0.0.1:" port "/;"
        print "        proxy_set_header Host $host;"
        print "        proxy_set_header X-Real-IP $remote_addr;"
        print "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;"
        print "        proxy_set_header X-Forwarded-Proto $scheme;"
        print "        proxy_set_header X-Script-Name /racing;"
        print "        proxy_connect_timeout 300s;"
        print "        proxy_read_timeout 300s;"
        print "        proxy_send_timeout 300s;"
        print "        proxy_buffering on;"
        print "    }"
        print ""
        print "    location /api/racing/ {"
        print "        proxy_pass http://127.0.0.1:" port "/api/;"
        print "        proxy_set_header Host $host;"
        print "        proxy_set_header X-Real-IP $remote_addr;"
        print "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;"
        print "        proxy_set_header X-Forwarded-Proto $scheme;"
        print "        proxy_connect_timeout 60s;"
        print "        proxy_read_timeout 60s;"
        print "        proxy_send_timeout 60s;"
        print "    }"
        print "    " end
        done=1
      }
      { print }
    ' "${SITE_AVAILABLE}" >"${tmp}"
    mv "${tmp}" "${SITE_AVAILABLE}"
  fi
fi

if [[ -f "${APP}/scripts/lib_racing_vps_probe.sh" ]]; then
  # shellcheck source=../scripts/lib_racing_vps_probe.sh
  source "${APP}/scripts/lib_racing_vps_probe.sh"
  football_vps_fix_nginx_upstream "${APP}" || true
else
  if [[ -f "${SITE_AVAILABLE}" ]]; then
    sed -i 's|127\.0\.0\.1:5001|127.0.0.1:8000|g' "${SITE_AVAILABLE}" 2>/dev/null || true
  fi
fi

if [[ -f /etc/nginx/sites-enabled/hibs-unified ]]; then
  if grep -qE '127\.0\.0\.1:5001|upstream hibs_football' /etc/nginx/sites-enabled/hibs-unified 2>/dev/null; then
    warn "disabling hibs-unified (dev :5001 upstream conflicts with production :8000)"
    rm -f /etc/nginx/sites-enabled/hibs-unified
  fi
fi

if command -v nginx >/dev/null 2>&1 && [[ -f "${SITE_AVAILABLE}" ]]; then
  nginx -t
  systemctl reload nginx
  log "nginx reloaded"
fi

if [[ -f /etc/systemd/system/hibs-racing.service ]]; then
  systemctl enable hibs-racing 2>/dev/null || true
  if ! systemctl is-active --quiet hibs-racing 2>/dev/null; then
    log "starting hibs-racing"
    systemctl start hibs-racing 2>/dev/null || warn "hibs-racing start failed — journalctl -u hibs-racing -n 30"
  fi
elif [[ ! -d "${RACING}" ]]; then
  warn "no hibs-racing at ${RACING} — deploy from Mac: ./scripts/deploy_racing_to_vps.sh"
fi

ping_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 12 "http://127.0.0.1:${RACING_PORT}/api/ping" 2>/dev/null || echo 000)"
pub_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "https://${PUBLIC}/racing/api/ping" 2>/dev/null || echo 000)"
log "racing localhost ping=${ping_code} public ping=${pub_code}"

if [[ "${ping_code}" != "200" ]]; then
  warn "racing :${RACING_PORT} not green — run vps_racing_hard_recovery.sh if needed"
fi

log "verify: curl -sS https://${PUBLIC}/racing/api/ping"

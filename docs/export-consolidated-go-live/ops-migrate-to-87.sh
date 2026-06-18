#!/usr/bin/env bash
# Migrate hibs-bet split stack (.73 + .75) → consolidated box 87.106.100.52
#
# Mac — print copy commands:
#   bash deploy/ops-migrate-to-87.sh --print-rsync
#
# New VPS — full bootstrap:
#   curl -fsSL https://raw.githubusercontent.com/mc8h7dxz6t-ui/hibs-bet/main/deploy/ops-migrate-to-87.sh | sudo bash
#   # or: cd /opt/hibs-bet && sudo bash deploy/ops-migrate-to-87.sh
#
# After rsync + git pull:
#   sudo bash deploy/ops-migrate-to-87.sh --skip-bootstrap
#
# After DNS A record → 87.106.100.52:
#   sudo bash deploy/ops-migrate-to-87.sh --post-dns
#
# Re-arm crons only:
#   sudo bash deploy/ops-migrate-to-87.sh --hands-off-only
set -euo pipefail

NEW_IP="${MIGRATE_NEW_IP:-87.106.100.52}"
OLD_MAIN="${MIGRATE_OLD_MAIN:-77.68.89.73}"
OLD_FVE="${MIGRATE_OLD_FVE:-77.68.89.75}"
PUBLIC="${HIBS_PUBLIC_HOST:-hibs-bet.co.uk}"
CERT_EMAIL="${CERTBOT_EMAIL:-}"
APP="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
TRADING="${TRADING_INSTALL_ROOT:-/opt/trading-core}"
FVE="${FVE_DEPLOY_PATH:-/opt/fve}"
REPO="${HIBS_SYNC_REPO:-mc8h7dxz6t-ui/hibs-bet}"
REF="${HIBS_SYNC_REF:-main}"

MODE="bootstrap"
for arg in "$@"; do
  case "${arg}" in
    --print-rsync) MODE="print-rsync" ;;
    --skip-bootstrap) MODE="skip-bootstrap" ;;
    --post-dns) MODE="post-dns" ;;
    --hands-off-only) MODE="hands-off-only" ;;
  esac
done

log() { echo "[migrate-87] $*"; }
warn() { echo "[migrate-87] WARN: $*" >&2; }

print_rsync() {
  cat <<EOF
# Run these from your Mac (after SSH keys work to old + new boxes).
# If .73 SSH is dead, use your provider web console to tar + download instead.

# Secrets
scp root@${OLD_MAIN}:/opt/hibs-bet/.env root@${NEW_IP}:/opt/hibs-bet/.env
scp root@${OLD_MAIN}:/opt/hibs-racing/.env root@${NEW_IP}:/opt/hibs-racing/.env
scp root@${OLD_MAIN}:/etc/trading_secrets root@${NEW_IP}:/etc/trading_secrets 2>/dev/null || true

# Football fixture cache (fixes /api/fve/fixtures count=0)
rsync -avz root@${OLD_MAIN}:/opt/hibs-bet/.cache/ root@${NEW_IP}:/opt/hibs-bet/.cache/

# Racing SQLite data
rsync -avz root@${OLD_MAIN}:/opt/hibs-racing/data/ root@${NEW_IP}:/opt/hibs-racing/data/

# Optional — FVE scrape-lines from old dedicated box (skip if empty)
rsync -avz root@${OLD_FVE}:/var/lib/fve/scrape-lines/ root@${NEW_IP}:/var/lib/fve/scrape-lines/ || true

# Fix ownership on new box
ssh root@${NEW_IP} 'chown -R www-data:www-data /opt/hibs-bet/.cache /opt/hibs-racing/data; chmod 640 /opt/hibs-bet/.env /opt/hibs-racing/.env; chmod 600 /etc/trading_secrets 2>/dev/null || true'
EOF
}

ensure_app_tree() {
  if [[ -d "${APP}/deploy" ]]; then
    return 0
  fi
  log "clone hibs-bet → ${APP}"
  mkdir -p "${APP}"
  if command -v git >/dev/null 2>&1; then
    git clone --depth 1 -b "${REF}" "https://github.com/${REPO}.git" "${APP}.clone"
    rsync -a "${APP}.clone/" "${APP}/"
    rm -rf "${APP}.clone"
  else
    curl -fsSL "https://github.com/${REPO}/archive/refs/heads/${REF}.tar.gz" | tar -xz -C /tmp
    SRC="$(find /tmp -maxdepth 1 -type d -name 'hibs-bet-*' | head -1)"
    rsync -a "${SRC}/" "${APP}/"
  fi
}

dns_on_new_box() {
  local resolved
  resolved="$(dig +short "${PUBLIC}" A 2>/dev/null | tail -1 || true)"
  [[ "${resolved}" == "${NEW_IP}" ]]
}

post_dns() {
  [[ "$(id -u)" -eq 0 ]] || { echo "run as root" >&2; exit 1; }
  ensure_app_tree

  log "check DNS: ${PUBLIC} should be ${NEW_IP}"
  if ! dns_on_new_box; then
    warn "DNS still not on ${NEW_IP} — got: $(dig +short "${PUBLIC}" A 2>/dev/null | tr '\n' ' ')"
    warn "Fix A record at registrar, wait 5–30 min, then re-run --post-dns"
    exit 1
  fi

  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq certbot python3-certbot-nginx nginx 2>/dev/null || \
    apt-get install -y -qq certbot python3-certbot-nginx

  if [[ ! -f /etc/nginx/sites-available/hibs-bet ]]; then
    cp "${APP}/deploy/hibs-bet.nginx.conf" /etc/nginx/sites-available/hibs-bet
    ln -sf /etc/nginx/sites-available/hibs-bet /etc/nginx/sites-enabled/hibs-bet
    rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
  fi
  export DEPLOY_PATH="${APP}" HIBS_RACING_DEPLOY_PATH="${RACING}" HIBS_PUBLIC_HOST="${PUBLIC}"
  bash "${APP}/deploy/apply-vps-racing-link.sh" 2>/dev/null || true
  bash "${APP}/deploy/apply-nginx-fve-line-trader.sh" 2>/dev/null || true
  nginx -t
  systemctl reload nginx

  if [[ -z "${CERT_EMAIL}" ]]; then
    CERT_EMAIL="$(grep -E '^HIBS_CERT_EMAIL=' "${APP}/.env" 2>/dev/null | tail -1 | cut -d= -f2- || true)"
  fi
  [[ -n "${CERT_EMAIL}" ]] || CERT_EMAIL="admin@${PUBLIC}"

  log "certbot for ${PUBLIC}"
  certbot --nginx -d "${PUBLIC}" -d "www.${PUBLIC}" \
    --non-interactive --agree-tos -m "${CERT_EMAIL}" --redirect || {
    warn "certbot failed — check: dig +short ${PUBLIC}; nginx -t; ufw allow 80 443"
    exit 1
  }

  bash "${APP}/deploy/ensure-vps-stack-wiring.sh" --repair || true
  systemctl restart hibs-bet hibs-racing nginx 2>/dev/null || true
  log "TLS OK — verify: curl -sS https://${PUBLIC}/api/ping"
}

hands_off_only() {
  [[ "$(id -u)" -eq 0 ]] || { echo "run as root" >&2; exit 1; }
  ensure_app_tree
  HIBS_VPS_IP="${NEW_IP}" HIBS_PUBLIC_HOST="${PUBLIC}" \
    bash "${APP}/scripts/install_four_stack_automation.sh"
}

skip_bootstrap() {
  [[ "$(id -u)" -eq 0 ]] || { echo "run as root" >&2; exit 1; }
  ensure_app_tree
  mkdir -p /etc/hibs-bet
  cat >/etc/hibs-bet/stack.env <<EOF
FVE_REMOTE_HOST=127.0.0.1
HIBS_PUBLIC_HOST=${PUBLIC}
HIBS_VPS_IP=${NEW_IP}
EOF
  chown -R www-data:www-data "${APP}/.cache" "${APP}/logs" 2>/dev/null || true
  [[ -f "${APP}/deploy/dedupe-env.sh" ]] && bash "${APP}/deploy/dedupe-env.sh" || true
  systemctl restart hibs-bet hibs-racing 2>/dev/null || true
  HIBS_UPSTREAM_BASE_URL=http://127.0.0.1:8000 HIBS_PUBLIC_HOST="${PUBLIC}" \
    DEPLOY_PATH="${APP}" FVE_DEPLOY_PATH="${FVE}" \
    bash "${APP}/deploy/apply-vps-fve-line-trader.sh" || true
  hands_off_only
  bash "${APP}/scripts/vps_three_stack_green.sh" --repair || true
}

full_bootstrap() {
  [[ "$(id -u)" -eq 0 ]] || { echo "run as root" >&2; exit 1; }
  ensure_app_tree
  if [[ -f "${APP}/scripts/bootstrap_consolidated_vps_go_live.sh" ]]; then
    HIBS_VPS_IP="${NEW_IP}" HIBS_PUBLIC_HOST="${PUBLIC}" \
      bash "${APP}/scripts/bootstrap_consolidated_vps_go_live.sh"
  else
    skip_bootstrap
  fi
}

case "${MODE}" in
  print-rsync) print_rsync ;;
  post-dns) post_dns ;;
  hands-off-only) hands_off_only ;;
  skip-bootstrap) skip_bootstrap ;;
  bootstrap) full_bootstrap ;;
esac

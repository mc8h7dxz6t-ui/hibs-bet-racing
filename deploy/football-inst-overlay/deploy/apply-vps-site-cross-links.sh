#!/usr/bin/env bash
# Idempotent football .env URL pointers — racing, trading, production host.
#
#   sudo bash /opt/hibs-bet/deploy/apply-vps-site-cross-links.sh
#   CROSS_LINK_RACING=auto CROSS_LINK_TRADING=1 sudo bash ...
set -euo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
PUBLIC="${HIBS_PUBLIC_HOST:-hibs-bet.co.uk}"
CROSS_LINK_RACING="${CROSS_LINK_RACING:-auto}"
CROSS_LINK_TRADING="${CROSS_LINK_TRADING:-0}"
CROSS_LINK_PUBLIC="${CROSS_LINK_PUBLIC:-path}"

log() { echo "[cross-links] $*"; }

[[ "$(id -u)" -eq 0 ]] || { echo "run as root: sudo bash $0" >&2; exit 1; }
[[ -f "${APP}/deploy/lib_env_upsert.sh" ]] || { echo "missing lib_env_upsert.sh" >&2; exit 1; }

# shellcheck source=lib_env_upsert.sh
source "${APP}/deploy/lib_env_upsert.sh"

if [[ -f /etc/hibs-bet/stack.env ]]; then
  # shellcheck disable=SC1091
  source /etc/hibs-bet/stack.env
  PUBLIC="${HIBS_PUBLIC_HOST:-${PUBLIC}}"
fi

touch "${APP}/.env"
env_dedupe_file "${APP}/.env"

racing_on=0
case "${CROSS_LINK_RACING}" in
  1|true|yes|on|auto) racing_on=1 ;;
esac

if [[ "${racing_on}" -eq 1 ]]; then
  if [[ "${CROSS_LINK_PUBLIC}" == "absolute" ]]; then
    env_upsert "${APP}/.env" HIBS_RACING_BASE_URL "https://${PUBLIC}/racing"
  else
    env_upsert "${APP}/.env" HIBS_RACING_BASE_URL "/racing"
  fi
  env_upsert "${APP}/.env" HIBS_PORTFOLIO_API_URL "/api/racing/portfolio/summary"
  env_upsert "${APP}/.env" HIBS_HEALTH_RACING_PROBE "1"
  log "racing cross-links set (base + portfolio API)"
fi

case "${CROSS_LINK_TRADING}" in
  1|true|yes|on)
    env_upsert "${APP}/.env" HIBS_TRADING_STATUS_URL "/harvested-execution"
    log "trading cross-link set"
    ;;
esac

env_upsert "${APP}/.env" HIBS_PRODUCTION_URL "https://${PUBLIC}"
env_upsert "${APP}/.env" HIBS_FOOTBALL_BASE_URL "https://${PUBLIC}"
chown www-data:www-data "${APP}/.env" 2>/dev/null || true

log "production host pointers → https://${PUBLIC}"

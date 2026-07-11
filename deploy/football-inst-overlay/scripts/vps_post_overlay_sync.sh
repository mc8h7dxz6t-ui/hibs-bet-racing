#!/usr/bin/env bash
# Post overlay sync — drift check, cross-links, cron arm, one repair cycle.
#
#   sudo bash /opt/hibs-bet/scripts/vps_post_overlay_sync.sh
set -euo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"

[[ "$(id -u)" -eq 0 ]] || { echo "run as root" >&2; exit 1; }

echo "==> vps_post_overlay_sync"

if [[ -f "${APP}/scripts/verify_vps_relative_paths.sh" ]]; then
  bash "${APP}/scripts/verify_vps_relative_paths.sh"
fi

if [[ -f "${APP}/deploy/apply-vps-site-cross-links.sh" ]]; then
  CROSS_LINK_RACING=auto bash "${APP}/deploy/apply-vps-site-cross-links.sh"
fi

if [[ -f "${APP}/deploy/apply-vps-racing-link.sh" ]]; then
  DEPLOY_PATH="${APP}" HIBS_RACING_DEPLOY_PATH="${RACING}" \
    bash "${APP}/deploy/apply-vps-racing-link.sh"
fi

if [[ -f "${APP}/deploy/install-hibs-cron-sudoers.sh" ]]; then
  bash "${APP}/deploy/install-hibs-cron-sudoers.sh"
fi
if [[ -f "${APP}/deploy/cron-hibs-infra-fallback.sh" ]]; then
  bash "${APP}/deploy/cron-hibs-infra-fallback.sh" --install
fi
if [[ -f "${APP}/deploy/cron-hibs-ops-automation.sh" ]]; then
  bash "${APP}/deploy/cron-hibs-ops-automation.sh" --install
fi

systemctl restart hibs-bet 2>/dev/null || true
sleep 3

if [[ -f "${APP}/scripts/verify_public_edge.sh" ]]; then
  bash "${APP}/scripts/verify_public_edge.sh" || true
fi

echo "post-overlay sync complete"

#!/usr/bin/env bash
# Drift guard — required deploy/automation scripts exist under DEPLOY_PATH.
#
#   bash /opt/hibs-bet/scripts/verify_vps_relative_paths.sh
set -euo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
fail=0

check() {
  local rel="$1"
  if [[ -f "${APP}/${rel}" ]]; then
    echo "OK   ${rel}"
  else
    echo "MISS ${rel}" >&2
    fail=1
  fi
}

echo "==> verify_vps_relative_paths app=${APP}"

for rel in \
  deploy/hibs-bet.nginx.conf \
  deploy/vps-sync-overlay-from-github.sh \
  deploy/vps-bootstrap-from-github.sh \
  deploy/apply-vps-racing-link.sh \
  deploy/apply-vps-site-cross-links.sh \
  deploy/cron-hibs-infra-fallback.sh \
  deploy/cron-hibs-ops-automation.sh \
  scripts/lib_football_vps_fallback.sh \
  scripts/lib_racing_vps_probe.sh \
  scripts/vps_football_hard_recovery.sh \
  scripts/vps_football_diagnose_502.sh \
  scripts/vps_football_ensure_nginx_production.sh \
  scripts/vps_full_stack_recovery.sh \
  scripts/vps_post_overlay_sync.sh \
  scripts/verify_public_edge.sh \
  scripts/vps_infra_fallback_cycle.sh \
  scripts/vps_three_stack_green.sh; do
  check "${rel}"
done

exit "${fail}"

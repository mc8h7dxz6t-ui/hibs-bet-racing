#!/usr/bin/env bash
# Bootstrap full-platform automation onto /opt/hibs-bet when GitHub branch isn't merged yet.
#
# Run on VPS as root:
#   curl -fsSL "https://raw.githubusercontent.com/mc8h7dxz6t-ui/hibs-bet-racing/cursor/full-platform-automation-export-7e4d/docs/export-full-platform-automation/bootstrap-vps.sh" | bash
#
# Or from a local clone:
#   sudo bash docs/export-full-platform-automation/bootstrap-vps.sh
set -euo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

[[ "$(id -u)" -eq 0 ]] || { echo "run as root" >&2; exit 1; }
[[ -d "${APP}" ]] || { echo "missing ${APP}" >&2; exit 1; }

echo "==> Install automation scripts into ${APP}"
install -m 755 "${SRC}/scripts/"*.sh "${APP}/scripts/"
install -m 755 "${SRC}/deploy/"*.sh "${APP}/deploy/"

echo "==> Sync hibs-bet main (base app)"
if [[ -f "${APP}/deploy/vps-sync-from-github.sh" ]]; then
  HIBS_SYNC_REF="${HIBS_SYNC_REF:-main}" APP_ROOT="${APP}" \
    bash "${APP}/deploy/vps-sync-from-github.sh"
  # Re-install scripts (sync may not have our branch files)
  install -m 755 "${SRC}/scripts/"*.sh "${APP}/scripts/"
  install -m 755 "${SRC}/deploy/"*.sh "${APP}/deploy/"
fi

echo "==> Run all-platform automation"
bash "${APP}/scripts/install_all_platform_automation.sh" --skip-sync

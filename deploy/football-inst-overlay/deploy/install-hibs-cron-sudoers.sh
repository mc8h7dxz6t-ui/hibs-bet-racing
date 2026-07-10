#!/usr/bin/env bash
# Allow www-data cron to run hands-off repair without password prompts.
#
#   sudo bash /opt/hibs-bet/deploy/install-hibs-cron-sudoers.sh
set -euo pipefail

APP="${APP_ROOT:-/opt/hibs-bet}"
DEST="/etc/sudoers.d/hibs-cron"
MARKER="# hibs-bet www-data cron (managed by install-hibs-cron-sudoers.sh)"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

# requiretty removed in sudo 1.9+ — omit Defaults line on modern distros (cron works without it).
SUDO_VER="$(sudo -V 2>/dev/null | awk '/Sudo version/ {print $3; exit}')"
SUDO_DEFAULTS=""
if [[ -n "${SUDO_VER}" ]] && dpkg --compare-versions "${SUDO_VER}" lt "1.9" 2>/dev/null; then
  SUDO_DEFAULTS="Defaults:www-data !requiretty"
fi

cat >"${DEST}" <<EOF
${MARKER}
${SUDO_DEFAULTS}
www-data ALL=(root) NOPASSWD: /bin/bash ${APP}/deploy/cron-hibs-hands-off.sh --run
www-data ALL=(root) NOPASSWD: /bin/bash ${APP}/deploy/cron-hibs-institutional-watchdog.sh --run
www-data ALL=(root) NOPASSWD: /bin/bash ${APP}/scripts/hands_off_cycle.sh
www-data ALL=(root) NOPASSWD: /bin/systemctl restart hibs-bet.service
www-data ALL=(root) NOPASSWD: /bin/systemctl restart hibs-racing.service
www-data ALL=(root) NOPASSWD: /bin/systemctl is-active hibs-bet.service
www-data ALL=(root) NOPASSWD: /bin/systemctl is-active hibs-racing.service
EOF
chmod 440 "${DEST}"
visudo -cf "${DEST}"
echo "Installed ${DEST}"

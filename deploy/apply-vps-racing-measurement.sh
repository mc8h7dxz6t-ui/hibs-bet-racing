#!/usr/bin/env bash
# Racing measurement profile — sale gates off by default, light health, settlement transparency.
#
#   sudo bash /opt/hibs-racing/deploy/apply-vps-racing-measurement.sh
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-racing}"
ENV_FILE="${APP_ROOT}/.env"
MARKER="# --- Racing measurement profile (hibs-racing deploy) ---"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

touch "${ENV_FILE}"
if grep -qF "${MARKER}" "${ENV_FILE}"; then
  tmp="$(mktemp)"
  awk -v m="${MARKER}" '
    $0 == m { skip=1; next }
    skip && /^HIBS_/ { next }
    skip && /^$/ { skip=0; next }
  ' "${ENV_FILE}" >"$tmp"
  mv "$tmp" "${ENV_FILE}"
fi

cat >>"${ENV_FILE}" <<EOF

${MARKER}
HIBS_PRODUCTION=1
HIBS_HEALTH_LIGHT=1
HIBS_HENERY_CORRECTION=1
HIBS_HENERY_GAMMA=1.10
HIBS_HARVILLE_CORRECTION=1
# Enable after OOS validation: HIBS_RACING_SALE_GATES=1
EOF

chown www-data:www-data "${ENV_FILE}" 2>/dev/null || true
chmod 640 "${ENV_FILE}" 2>/dev/null || true
echo "==> Racing measurement profile written to ${ENV_FILE}"
echo "    Restart: systemctl restart hibs-racing"

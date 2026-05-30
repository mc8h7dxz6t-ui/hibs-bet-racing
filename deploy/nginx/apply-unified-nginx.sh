#!/usr/bin/env bash
# Install unified hibs nginx reverse proxy (football :5001, racing :5003).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONF_SRC="${ROOT}/deploy/nginx/hibs-unified.conf"
CONF_DST="/etc/nginx/sites-available/hibs-unified"
ENABLED="/etc/nginx/sites-enabled/hibs-unified"

if [[ ! -f "${CONF_SRC}" ]]; then
  echo "Missing ${CONF_SRC}" >&2
  exit 1
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Re-run with sudo: sudo bash deploy/nginx/apply-unified-nginx.sh" >&2
  exit 1
fi

command -v nginx >/dev/null || { echo "Install nginx first: apt-get install -y nginx" >&2; exit 1; }

cp "${CONF_SRC}" "${CONF_DST}"
ln -sf "${CONF_DST}" "${ENABLED}"

# Drop default site if present (optional — avoids port 80 conflict)
if [[ -f /etc/nginx/sites-enabled/default ]]; then
  rm -f /etc/nginx/sites-enabled/default
fi

nginx -t
systemctl reload nginx

echo "Unified proxy installed."
echo "  Football → http://127.0.0.1/dashboard/football/"
echo "  Racing   → http://127.0.0.1/dashboard/racing/"
echo "  Health   → http://127.0.0.1/health"

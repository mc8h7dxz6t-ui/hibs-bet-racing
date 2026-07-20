#!/usr/bin/env bash
# Enable exchange place EV shadow lane (Gate3) — production flag stays off until operator flip.
#
#   sudo bash /opt/hibs-racing/deploy/apply-vps-exchange-ev.sh
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-racing}"
ENV_FILE="${APP_ROOT}/.env"
MARKER="# --- Exchange place EV shadow (hibs-racing deploy) ---"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

touch "${ENV_FILE}"
if grep -qF "${MARKER}" "${ENV_FILE}"; then
  tmp="$(mktemp)"
  awk -v m="${MARKER}" '
    $0 == m { skip=1; next }
    skip && /^HIBS_EXCHANGE_/ { next }
    skip && /^HIBS_KELLY_FRACTION=/ { next }
    skip && /^HIBS_MAX_RUNNER_RISK_PCT=/ { next }
    skip && /^$/ { skip=0; next }
  ' "${ENV_FILE}" >"$tmp"
  mv "$tmp" "${ENV_FILE}"
fi

cat >>"${ENV_FILE}" <<EOF

${MARKER}
HIBS_EXCHANGE_EV_SHADOW=1
HIBS_EXCHANGE_EV_PRODUCTION=0
HIBS_EXCHANGE_COMMISSION=0.02
HIBS_KELLY_FRACTION=0.25
HIBS_MAX_RUNNER_RISK_PCT=0.02
HIBS_EXCHANGE_EV_MIN_COVERAGE_PCT=50
EOF

chown www-data:www-data "${ENV_FILE}" 2>/dev/null || true
chmod 640 "${ENV_FILE}" 2>/dev/null || true

echo "==> Exchange EV shadow profile written to ${ENV_FILE}"
echo "    Re-score:  cd ${APP_ROOT} && source .venv/bin/activate && set -a && source .env && set +a && hibs-racing score-card --odds-source matchbook"
echo "    Status:    hibs-racing exchange-ev-status"
echo "    Production flip (manual after unlock): HIBS_EXCHANGE_EV_PRODUCTION=1"
echo "    Restart:   systemctl restart hibs-racing"

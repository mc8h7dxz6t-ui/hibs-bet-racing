#!/usr/bin/env bash
# Idempotent upsert of McFadden win engine env flags into hibs-bet-racing .env
#
#   sudo bash deploy/apply-win-engine-env.sh           # staging (active=false)
#   sudo bash deploy/apply-win-engine-env.sh --active  # Phase 4 go-live
set -euo pipefail

ENV_FILE="${HIBS_RACING_ENV_FILE:-/opt/hibs-bet-racing/.env}"
ACTIVE="${HIBS_WIN_ENGINE_ACTIVE:-false}"

for arg in "$@"; do
  case "${arg}" in
    --active) ACTIVE=true ;;
    --inactive) ACTIVE=false ;;
  esac
done

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: ${ENV_FILE} not found" >&2
  exit 1
fi

upsert() {
  local key="$1" val="$2"
  if grep -q "^${key}=" "${ENV_FILE}" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" "${ENV_FILE}"
  else
    printf '\n%s=%s\n' "${key}" "${val}" >> "${ENV_FILE}"
  fi
}

MARKER="# McFadden Win Engine Staging Configuration"
if ! grep -qF "${MARKER}" "${ENV_FILE}" 2>/dev/null; then
  cat >> "${ENV_FILE}" <<EOF

${MARKER} (Leave as false initially)
EOF
fi

upsert "HIBS_WIN_ENGINE_ACTIVE" "${ACTIVE}"
upsert "HIBS_RACING_WIN_BRIER_PASS_MAX" "0.185"
upsert "HIBS_RACING_MIN_WIN_CALIBRATION_N" "100"

echo "Updated ${ENV_FILE}:"
grep -E '^HIBS_WIN_ENGINE_ACTIVE=|^HIBS_RACING_WIN_BRIER_PASS_MAX=|^HIBS_RACING_MIN_WIN_CALIBRATION_N=' "${ENV_FILE}" || true
echo
echo "Restart racing to apply: sudo systemctl restart hibs-racing"

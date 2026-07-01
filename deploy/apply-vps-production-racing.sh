#!/usr/bin/env bash
# Production racing profile — exit observation lane, enforce institutional gates.
#
# Run after observation period + preflight_matchbook_post_observation.sh passes.
#
#   sudo bash /opt/hibs-racing/deploy/apply-vps-production-racing.sh
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-racing}"
ENV_FILE="${APP_ROOT}/.env"
MARKER="# --- VPS racing production (observation lane off) ---"
LEGACY_MARKER="# --- VPS racing scrape-first institutional ---"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

[[ -d "${APP_ROOT}/src" ]] || { echo "Missing ${APP_ROOT}" >&2; exit 1; }
touch "${ENV_FILE}"

strip_block() {
  local m="$1"
  grep -qF "${m}" "${ENV_FILE}" 2>/dev/null || return 0
  awk -v m="${m}" '$0 == m {skip=1; next} skip && /^HIBS_/ {next} skip && /^RACING_/ {next} skip && /^$/ {skip=0; next} {print}' \
    "${ENV_FILE}" >"${ENV_FILE}.tmp" && mv "${ENV_FILE}.tmp" "${ENV_FILE}"
}

strip_block "${MARKER}"

cat >>"${ENV_FILE}" <<EOF

${MARKER}
HIBS_RACING_PRODUCTION=1
HIBS_OBSERVATION_LANE=0
HIBS_HEALTH_LIGHT=0
HIBS_DISABLE_UI_REFRESH=1
HIBS_RANKER_REQUIRE_MANIFEST=0
LOG_DIR=/var/log/hibs-racing
EOF

# Upsert critical keys (idempotent)
upsert() {
  local key="$1" val="$2"
  if grep -q "^${key}=" "${ENV_FILE}" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" "${ENV_FILE}"
  else
    echo "${key}=${val}" >>"${ENV_FILE}"
  fi
}
upsert HIBS_RACING_PRODUCTION 1
upsert HIBS_OBSERVATION_LANE 0
upsert HIBS_HEALTH_LIGHT 0

chown www-data:www-data "${ENV_FILE}" 2>/dev/null || true
chmod 640 "${ENV_FILE}" 2>/dev/null || true

# Scrape-first odds lane (non-destructive if already applied)
if [[ -f "${APP_ROOT}/deploy/apply-vps-racing-scrape-first-institutional.sh" ]]; then
  bash "${APP_ROOT}/deploy/apply-vps-racing-scrape-first-institutional.sh"
fi

systemctl restart hibs-racing 2>/dev/null || true
sleep 4
systemctl is-active hibs-racing 2>/dev/null || echo "WARN: hibs-racing not active"

echo "==> production racing profile applied (observation lane OFF)"
echo "Verify:"
echo "  bash ${APP_ROOT}/scripts/preflight_matchbook_post_observation.sh"
echo "  bash ${APP_ROOT}/scripts/verify_racing_institutional_readiness.sh"
echo "  curl -s http://127.0.0.1:5003/api/health | python3 -m json.tool | head -50"

PY="${APP_ROOT}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY="python3"
OBS="$("${PY}" -c "from hibs_racing.models.ranker_preflight import observation_lane_enabled; print(observation_lane_enabled())" 2>/dev/null || echo unknown)"
echo "observation_lane_enabled=${OBS}"

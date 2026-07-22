#!/usr/bin/env bash
# Idempotent upsert of McFadden win engine env flags into hibs-racing .env
#
# VPS default path is /opt/hibs-racing (see hibs-racing.service), not /opt/hibs-bet-racing.
#
#   sudo bash deploy/apply-win-engine-env.sh           # staging (active=false)
#   sudo bash deploy/apply-win-engine-env.sh --active  # Phase 4 go-live
#
# Override when needed:
#   sudo HIBS_RACING_ENV_FILE=/opt/hibs-racing/.env bash deploy/apply-win-engine-env.sh
set -euo pipefail

_resolve_env_file() {
  if [[ -n "${HIBS_RACING_ENV_FILE:-}" ]]; then
    echo "${HIBS_RACING_ENV_FILE}"
    return 0
  fi

  local deploy="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"

  if [[ -f "${deploy}/.env" ]]; then
    echo "${deploy}/.env"
    return 0
  fi

  if [[ -f /etc/systemd/system/hibs-racing.service ]]; then
    local unit_env
    unit_env="$(
      grep -E '^EnvironmentFile=-?' /etc/systemd/system/hibs-racing.service 2>/dev/null \
        | head -1 \
        | sed 's/^EnvironmentFile=-//' \
        || true
    )"
    if [[ -n "${unit_env}" ]]; then
      echo "${unit_env}"
      return 0
    fi
  fi

  for candidate in \
    "/opt/hibs-racing/.env" \
    "/opt/hibs-bet-racing/.env" \
    "${deploy}/.env"; do
    if [[ -f "${candidate}" ]]; then
      echo "${candidate}"
      return 0
    fi
  done

  for root in "/opt/hibs-racing" "${deploy}" "/opt/hibs-bet-racing"; do
    if [[ -d "${root}" ]]; then
      echo "${root}/.env"
      return 0
    fi
  done

  echo "/opt/hibs-racing/.env"
}

ENV_FILE="$(_resolve_env_file)"
ACTIVE="${HIBS_WIN_ENGINE_ACTIVE:-false}"

for arg in "$@"; do
  case "${arg}" in
    --active) ACTIVE=true ;;
    --inactive) ACTIVE=false ;;
  esac
done

if [[ ! -f "${ENV_FILE}" ]]; then
  root="$(dirname "${ENV_FILE}")"
  if [[ ! -d "${root}" ]]; then
    echo "ERROR: racing deploy path ${root} not found." >&2
    echo "  Sync first: sudo HIBS_SYNC_REF=main bash /opt/hibs-bet/deploy/vps-sync-racing-from-github.sh" >&2
    echo "  Or set:      sudo HIBS_RACING_ENV_FILE=/opt/hibs-racing/.env bash $0" >&2
    exit 1
  fi
  touch "${ENV_FILE}"
  chown www-data:www-data "${ENV_FILE}" 2>/dev/null || true
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

upsert "HIBS_WIN_ENGINE_CONFIGURED" "1"
upsert "HIBS_WIN_ENGINE_ACTIVE" "${ACTIVE}"
upsert "HIBS_RACING_WIN_BRIER_PASS_MAX" "0.185"
upsert "HIBS_RACING_MIN_WIN_CALIBRATION_N" "100"

echo "Updated ${ENV_FILE}:"
grep -E '^HIBS_WIN_ENGINE_CONFIGURED=|^HIBS_WIN_ENGINE_ACTIVE=|^HIBS_RACING_WIN_BRIER_PASS_MAX=|^HIBS_RACING_MIN_WIN_CALIBRATION_N=' "${ENV_FILE}" || true
echo
echo "Restart racing to apply: sudo systemctl restart hibs-racing"

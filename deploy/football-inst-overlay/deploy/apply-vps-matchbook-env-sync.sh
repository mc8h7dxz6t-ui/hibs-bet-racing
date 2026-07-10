#!/usr/bin/env bash
# Sync Matchbook credentials: local racing .env → VPS racing + optional FVE .env.
#
# On main VPS (after preflight_matchbook_funded.sh GREEN on Mac):
#   sudo bash /opt/hibs-bet/deploy/apply-vps-matchbook-env-sync.sh
#
# Optional FVE box (SSH from main):
#   sudo FVE_REMOTE_HOST=77.68.89.75 FVE_DEPLOY_PATH=/opt/football-app \
#     bash /opt/hibs-bet/deploy/apply-vps-matchbook-env-sync.sh
set -euo pipefail

LIB_ROOT="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING_ROOT="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
RACING_ENV="${RACING_ROOT}/.env"
FVE_REMOTE_HOST="${FVE_REMOTE_HOST:-}"
FVE_DEPLOY_PATH="${FVE_DEPLOY_PATH:-/opt/football-app}"

log() { echo "[matchbook-sync] $*"; }

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

if [[ ! -f "${LIB_ROOT}/scripts/lib_matchbook_env.sh" ]]; then
  echo "ERROR: ${LIB_ROOT}/scripts/lib_matchbook_env.sh missing" >&2
  exit 1
fi

# shellcheck source=../scripts/lib_matchbook_env.sh
source "${LIB_ROOT}/scripts/lib_matchbook_env.sh"

upsert_env() {
  local file="$1"
  shift
  [[ -f "$file" ]] || touch "$file"
  while [[ $# -gt 0 ]]; do
    local key="${1%%=*}"
    local val="${1#*=}"
    if grep -qE "^${key}=" "$file" 2>/dev/null; then
      sed -i "s|^${key}=.*|${key}=${val}|" "$file"
    else
      echo "${key}=${val}" >>"$file"
    fi
    shift
  done
}

SOURCE_ENV="${MATCHBOOK_SOURCE_ENV:-}"

_discover_matchbook_source() {
  if [[ -n "${SOURCE_ENV}" ]]; then
    echo "${SOURCE_ENV}"
    return
  fi
  local f
  for f in \
    "${RACING_ENV}" \
    "${FVE_DEPLOY_PATH}/.env" \
    "/opt/fve/.env" \
    "/opt/football-app/.env" \
    "${LIB_ROOT}/.env" \
    "/etc/trading_secrets"; do
    if [[ -f "${f}" ]] && \
       grep -qE '^MATCHBOOK_(USER|USERNAME)=' "${f}" 2>/dev/null && \
       grep -qE '^MATCHBOOK_PASSWORD=' "${f}" 2>/dev/null; then
      echo "${f}"
      return
    fi
  done
  echo "${RACING_ENV}"
}

SOURCE_ENV="$(_discover_matchbook_source)"

log "load creds from ${SOURCE_ENV}"
matchbook_load_env "${SOURCE_ENV}"
if ! matchbook_credentials_ok; then
  echo "ERROR: MATCHBOOK_USER/PASSWORD not found in ${SOURCE_ENV}" >&2
  echo "Searched: racing, FVE (/opt/fve, /opt/football-app), hibs-bet, /etc/trading_secrets" >&2
  echo "Find source: for f in /opt/fve/.env /opt/football-app/.env /opt/hibs-bet/.env; do grep MATCHBOOK \"\$f\" 2>/dev/null; done" >&2
  echo "Then: sudo MATCHBOOK_SOURCE_ENV=/path/to/.env bash $0" >&2
  exit 1
fi
if [[ "${SOURCE_ENV}" != "${RACING_ENV}" ]]; then
  log "using shared feed source: ${SOURCE_ENV}"
fi
user="$(matchbook_user_value)"

log "1/3 — racing ${RACING_ENV}"
mkdir -p "${RACING_ROOT}"
upsert_env "${RACING_ENV}" \
  "MATCHBOOK_USER=${user}" \
  "MATCHBOOK_USERNAME=${user}" \
  "MATCHBOOK_PASSWORD=${MATCHBOOK_PASSWORD}"
chown www-data:www-data "${RACING_ENV}" 2>/dev/null || true
chmod 640 "${RACING_ENV}" 2>/dev/null || true

log "2/3 — probe login from VPS"
if bash "${LIB_ROOT}/scripts/preflight_matchbook_funded.sh" "${RACING_ENV}" --probe-edge; then
  log "VPS session OK"
else
  log "WARN VPS login failed — UK IP / funded balance / API flag?"
fi

if [[ -n "${FVE_REMOTE_HOST}" ]]; then
  log "3/3 — push to FVE ${FVE_REMOTE_HOST}:${FVE_DEPLOY_PATH}/.env"
  ssh -o BatchMode=yes -o ConnectTimeout=12 "root@${FVE_REMOTE_HOST}" bash -s <<EOF
set -euo pipefail
FVE_ENV="${FVE_DEPLOY_PATH}/.env"
touch "\${FVE_ENV}"
upsert() {
  local file="\$1" key="\$2" val="\$3"
  if grep -qE "^\${key}=" "\${file}" 2>/dev/null; then
    sed -i "s|^\${key}=.*|\${key}=\${val}|" "\${file}"
  else
    echo "\${key}=\${val}" >>"\${file}"
  fi
}
upsert "\${FVE_ENV}" MATCHBOOK_USERNAME "${user}"
upsert "\${FVE_ENV}" MATCHBOOK_PASSWORD "${MATCHBOOK_PASSWORD}"
echo "FVE .env updated"
EOF
else
  log "3/3 — skip FVE (set FVE_REMOTE_HOST to sync arb box)"
fi

log "done — restart racing unit if deployed:"
echo "  systemctl restart hibs-racing 2>/dev/null || true"
echo "  bash ${LIB_ROOT}/scripts/vps_racing_value_lane_recovery.sh"

#!/usr/bin/env bash
# Bootstrap + run autonomous install when /opt/hibs-racing/deploy/vps-autonomous-install.sh is missing.
#
#   sudo bash /opt/hibs-bet/deploy/vps-bootstrap-autonomous.sh
#   curl not required — ships in hibs-bet-racing branch and football overlay.
set -euo pipefail

BET="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
REF="${HIBS_RACING_SYNC_REF:-cursor/robust-scrape-inst-7e4d}"
INSTALL="${RACING}/deploy/vps-autonomous-install.sh"

log() { echo "[bootstrap] $*"; }
warn() { echo "[bootstrap] WARN: $*" >&2; }

[[ "$(id -u)" -eq 0 ]] || { echo "run as root: sudo bash $0" >&2; exit 1; }

if [[ -f "${INSTALL}" ]]; then
  log "found ${INSTALL} — running"
  exec bash "${INSTALL}" "$@"
fi

log "autonomous installer missing — syncing racing branch ${REF}"

if [[ -f "${BET}/deploy/vps-sync-racing-from-github.sh" ]]; then
  HIBS_RACING_SYNC_REF="${REF}" HIBS_RACING_DEPLOY_PATH="${RACING}" \
    bash "${BET}/deploy/vps-sync-racing-from-github.sh"
elif [[ -d "${RACING}/.git" ]]; then
  command -v git >/dev/null || { echo "git required" >&2; exit 1; }
  git -C "${RACING}" fetch --depth 1 origin "${REF}" 2>/dev/null || git -C "${RACING}" fetch origin "${REF}"
  git -C "${RACING}" checkout "${REF}" 2>/dev/null || git -C "${RACING}" checkout -B "${REF}" "origin/${REF}"
else
  TOKEN_FILE="${HIBS_RACING_GITHUB_TOKEN_FILE:-/etc/hibs-bet/secrets/racing_github_token}"
  GIT_URL="https://github.com/mc8h7dxz6t-ui/hibs-bet-racing.git"
  if [[ -f "${TOKEN_FILE}" ]]; then
    TOK="$(tr -d '[:space:]' <"${TOKEN_FILE}")"
    [[ -n "${TOK}" ]] && GIT_URL="https://${TOK}@github.com/mc8h7dxz6t-ui/hibs-bet-racing.git"
  fi
  rm -rf "${RACING}.bootstrap"
  git clone --depth 1 --branch "${REF}" "${GIT_URL}" "${RACING}.bootstrap"
  mkdir -p "${RACING}"
  rsync -a "${RACING}.bootstrap/" "${RACING}/"
  rm -rf "${RACING}.bootstrap"
fi

if [[ ! -f "${INSTALL}" ]]; then
  warn "still missing ${INSTALL} after sync"
  echo "Try: HIBS_RACING_SYNC_REF=${REF} bash ${BET}/deploy/vps-sync-racing-from-github.sh" >&2
  exit 1
fi

log "running ${INSTALL}"
exec bash "${INSTALL}" "$@"

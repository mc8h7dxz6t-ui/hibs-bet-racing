#!/usr/bin/env bash
# Sync hibs-racing from GitHub (rsync deploy — /opt/hibs-racing is NOT a git repo).
#
#   sudo HIBS_RACING_SYNC_REF=main bash /opt/hibs-racing/deploy/vps-sync-racing-from-github.sh
#   sudo HIBS_RACING_SYNC_REF=cursor/gate-config-alignment-12e0 bash ...
#
# Private repo token (one-time):
#   sudo mkdir -p /etc/hibs-bet/secrets
#   sudo bash -c 'echo ghp_YOUR_PAT > /etc/hibs-bet/secrets/racing_github_token'
#   sudo chmod 600 /etc/hibs-bet/secrets/racing_github_token
#
set -euo pipefail

RACING_ROOT="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
REF="${HIBS_RACING_SYNC_REF:-main}"
REPO="${HIBS_RACING_SYNC_REPO:-mc8h7dxz6t-ui/hibs-bet-racing}"
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

command -v curl >/dev/null || { echo "curl required" >&2; exit 1; }
command -v tar >/dev/null || { echo "tar required" >&2; exit 1; }
command -v rsync >/dev/null || { echo "rsync required" >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

SRC=""
SYNC_SOURCE="github_archive"
ARCHIVE_URL="https://github.com/${REPO}/archive/refs/heads/${REF}.tar.gz"
echo "==> fetch ${ARCHIVE_URL}"
if curl -fsSL "${ARCHIVE_URL}" -o "${TMP}/archive.tar.gz" 2>/dev/null; then
  tar -xzf "${TMP}/archive.tar.gz" -C "${TMP}"
  SRC="$(find "${TMP}" -maxdepth 1 -type d -name 'hibs-bet-racing-*' | head -1)"
fi

if [[ -z "${SRC}" || ! -d "${SRC}" ]]; then
  echo "==> archive unavailable (private repo?) — trying git clone"
  command -v git >/dev/null || { echo "git required for fallback" >&2; exit 1; }
  export GIT_TERMINAL_PROMPT=0
  GIT_URL="https://github.com/${REPO}.git"
  TOKEN_FILE="${HIBS_RACING_GITHUB_TOKEN_FILE:-/etc/hibs-bet/secrets/racing_github_token}"
  TOK=""
  if [[ -n "${HIBS_RACING_GITHUB_TOKEN:-}" ]]; then
    TOK="${HIBS_RACING_GITHUB_TOKEN}"
  elif [[ -f "${TOKEN_FILE}" ]]; then
    TOK="$(tr -d '[:space:]' <"${TOKEN_FILE}")"
  fi
  if [[ -z "${TOK}" ]]; then
    cat >&2 <<EOF
ERROR: private repo — GitHub PAT required (do NOT use git pull in /opt/hibs-racing).

  sudo mkdir -p /etc/hibs-bet/secrets
  sudo bash -c 'echo ghp_YOUR_PAT > /etc/hibs-bet/secrets/racing_github_token'
  sudo chmod 600 /etc/hibs-bet/secrets/racing_github_token
  sudo HIBS_RACING_SYNC_REF=${REF} bash $0
EOF
    exit 1
  fi
  GIT_URL="https://${TOK}@github.com/${REPO}.git"
  rm -rf "${RACING_ROOT}.gitclone"
  git -c credential.helper= clone --depth 1 --branch "${REF}" "${GIT_URL}" "${RACING_ROOT}.gitclone"
  SRC="${RACING_ROOT}.gitclone"
  SYNC_SOURCE="github_git_clone"
fi

[[ -n "${SRC}" && -d "${SRC}" ]] || { echo "sync failed — check ref=${REF}" >&2; exit 1; }

mkdir -p "${RACING_ROOT}"
echo "==> rsync ${SRC}/ -> ${RACING_ROOT}/ (preserve .env, data, .venv)"
rsync -a \
  --exclude '.git/' \
  --exclude '.env' \
  --exclude '.venv/' \
  --exclude 'data/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  "${SRC}/" "${RACING_ROOT}/"
rm -rf "${RACING_ROOT}.gitclone" 2>/dev/null || true

cat >"${RACING_ROOT}/.deploy-revision" <<EOF
revision=${REF}@${SYNC_SOURCE}
deployed_at=${STAMP}
service=hibs-racing
sync_source=${SYNC_SOURCE}
EOF
chown www-data:www-data "${RACING_ROOT}/.deploy-revision" 2>/dev/null || true

echo "==> pip install -e"
cd "${RACING_ROOT}"
if [[ ! -x .venv/bin/pip ]]; then
  python3 -m venv .venv
fi
find .venv/lib -type d -name '~*' -prune -exec rm -rf {} + 2>/dev/null || true
.venv/bin/pip install -q -r requirements.txt
.venv/bin/pip install -q -e . 2>/dev/null || true

BET_ROOT="${HIBS_BET_DEPLOY_PATH:-/opt/hibs-bet}"
for req in hibs-racing-web-requirements.txt hibs-racing-vps-extras.txt; do
  [[ -f "${BET_ROOT}/deploy/${req}" ]] && .venv/bin/pip install -q -r "${BET_ROOT}/deploy/${req}" || true
done

chown -R www-data:www-data "${RACING_ROOT}" 2>/dev/null || true
systemctl restart hibs-racing 2>/dev/null || true
echo "OK: racing synced ref=${REF} at ${STAMP} via ${SYNC_SOURCE}"
cat "${RACING_ROOT}/.deploy-revision"

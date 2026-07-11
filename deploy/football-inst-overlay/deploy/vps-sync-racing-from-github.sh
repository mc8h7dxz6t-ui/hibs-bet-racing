#!/usr/bin/env bash
# Sync hibs-racing from GitHub archive (no Mac rsync).
#
#   sudo HIBS_RACING_SYNC_REF=main bash /opt/hibs-bet/deploy/vps-sync-racing-from-github.sh
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
  echo "==> archive unavailable (private repo?) — trying git"
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
  if [[ -n "${TOK}" ]]; then
    GIT_URL="https://${TOK}@github.com/${REPO}.git"
  fi
  if [[ -d "${RACING_ROOT}/.git" ]]; then
    if [[ -z "${TOK}" ]]; then
      git -C "${RACING_ROOT}" remote set-url origin "${GIT_URL}" 2>/dev/null || true
    fi
    if ! git -C "${RACING_ROOT}" -c credential.helper= fetch --depth 1 origin "${REF}" 2>/dev/null; then
      if ! git -C "${RACING_ROOT}" -c credential.helper= fetch origin "${REF}" 2>/dev/null; then
        cat >&2 <<EOF
ERROR: git fetch failed (private repo needs a token).

Fix (one-time):
  sudo mkdir -p /etc/hibs-bet/secrets
  sudo bash -c 'echo YOUR_GITHUB_PAT > /etc/hibs-bet/secrets/racing_github_token'
  sudo chmod 600 /etc/hibs-bet/secrets/racing_github_token

Or inline for this session:
  export HIBS_RACING_GITHUB_TOKEN=ghp_xxxxxxxx
  sudo -E HIBS_RACING_SYNC_REF=${REF} bash $0

No git? Arm automation from football tree only:
  sudo bash ${HIBS_BET_DEPLOY_PATH:-/opt/hibs-bet}/deploy/vps-arm-hands-off-no-racing-sync.sh
EOF
        exit 1
      fi
    fi
    git -C "${RACING_ROOT}" checkout "${REF}" 2>/dev/null || git -C "${RACING_ROOT}" checkout -B "${REF}" "origin/${REF}" 2>/dev/null || true
    SRC="${RACING_ROOT}"
    SYNC_SOURCE="github_git_pull"
  else
    if [[ -z "${TOK}" ]]; then
      cat >&2 <<EOF
ERROR: cannot clone private repo without a GitHub token (no interactive login).

Fix (one-time):
  sudo mkdir -p /etc/hibs-bet/secrets
  sudo bash -c 'echo YOUR_GITHUB_PAT > /etc/hibs-bet/secrets/racing_github_token'
  sudo chmod 600 /etc/hibs-bet/secrets/racing_github_token
  sudo HIBS_RACING_SYNC_REF=${REF} bash $0

Or:
  export HIBS_RACING_GITHUB_TOKEN=ghp_xxxxxxxx
  sudo -E HIBS_RACING_SYNC_REF=${REF} bash $0

No git? Arm automation from football tree only:
  sudo bash ${HIBS_BET_DEPLOY_PATH:-/opt/hibs-bet}/deploy/vps-arm-hands-off-no-racing-sync.sh
EOF
      exit 1
    fi
    rm -rf "${RACING_ROOT}.gitclone"
    if ! git -c credential.helper= clone --depth 1 --branch "${REF}" "${GIT_URL}" "${RACING_ROOT}.gitclone"; then
      echo "git clone failed — check PAT has repo read access to ${REPO}" >&2
      exit 1
    fi
    SRC="${RACING_ROOT}.gitclone"
    SYNC_SOURCE="github_git_clone"
  fi
fi

[[ -n "${SRC}" && -d "${SRC}" ]] || { echo "sync failed — check ref=${REF}" >&2; exit 1; }

mkdir -p "${RACING_ROOT}"
if [[ "${SRC}" != "${RACING_ROOT}" ]]; then
  echo "==> rsync ${SRC}/ -> ${RACING_ROOT}/ (preserve .env, data)"
  rsync -a \
    --exclude '.git/' \
    --exclude '.env' \
    --exclude '.venv/' \
    --exclude 'data/' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    "${SRC}/" "${RACING_ROOT}/"
fi
rm -rf "${RACING_ROOT}.gitclone" 2>/dev/null || true

cat >"${RACING_ROOT}/.deploy-revision" <<EOF
revision=${REF}@${SYNC_SOURCE}
deployed_at=${STAMP}
service=hibs-racing
sync_source=${SYNC_SOURCE}
EOF
chown www-data:www-data "${RACING_ROOT}/.deploy-revision"

echo "==> pip install"
cd "${RACING_ROOT}"
if [[ ! -x .venv/bin/pip ]]; then
  python3 -m venv .venv
fi
# Interrupted pip uninstalls leave ~package dist-info dirs — clean before reinstall.
find .venv/lib -type d -name '~*' -prune -exec rm -rf {} + 2>/dev/null || true
.venv/bin/pip install -q -r requirements.txt
[[ -f pyproject.toml || -f setup.py ]] && .venv/bin/pip install -q -e . || true

BET_ROOT="${HIBS_BET_DEPLOY_PATH:-/opt/hibs-bet}"
if [[ -f "${BET_ROOT}/deploy/hibs-racing-web-requirements.txt" ]]; then
  .venv/bin/pip install -q -r "${BET_ROOT}/deploy/hibs-racing-web-requirements.txt" || true
fi
if [[ -f "${BET_ROOT}/deploy/hibs-racing-vps-extras.txt" ]]; then
  .venv/bin/pip install -q -r "${BET_ROOT}/deploy/hibs-racing-vps-extras.txt" || true
fi

if [[ -f "${BET_ROOT}/deploy/hibs-racing.service" ]]; then
  cp "${BET_ROOT}/deploy/hibs-racing.service" /etc/systemd/system/hibs-racing.service
  systemctl daemon-reload
fi
if [[ -f "${BET_ROOT}/deploy/gunicorn-racing.conf.py" ]]; then
  mkdir -p "${RACING_ROOT}/deploy"
  cp "${BET_ROOT}/deploy/gunicorn-racing.conf.py" "${RACING_ROOT}/deploy/gunicorn-racing.conf.py"
fi

chown -R www-data:www-data "${RACING_ROOT}"
systemctl restart hibs-racing 2>/dev/null || true
sleep 3
systemctl is-active hibs-racing 2>/dev/null || echo "WARN: hibs-racing not active yet"

echo ""
curl -fsS --max-time 10 "http://127.0.0.1:5003/api/ping" 2>/dev/null | head -c 200 || true
echo ""
echo "OK: racing synced ref=${REF} at ${STAMP}"

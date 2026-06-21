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
  GIT_URL="https://github.com/${REPO}.git"
  TOKEN_FILE="${HIBS_RACING_GITHUB_TOKEN_FILE:-/etc/hibs-bet/secrets/racing_github_token}"
  if [[ -n "${HIBS_RACING_GITHUB_TOKEN:-}" ]]; then
    GIT_URL="https://${HIBS_RACING_GITHUB_TOKEN}@github.com/${REPO}.git"
  elif [[ -f "${TOKEN_FILE}" ]]; then
    TOK="$(tr -d '[:space:]' <"${TOKEN_FILE}")"
    [[ -n "${TOK}" ]] && GIT_URL="https://${TOK}@github.com/${REPO}.git"
  fi
  if [[ -d "${RACING_ROOT}/.git" ]]; then
    git -C "${RACING_ROOT}" fetch --depth 1 origin "${REF}" 2>/dev/null || git -C "${RACING_ROOT}" fetch origin "${REF}"
    git -C "${RACING_ROOT}" checkout "${REF}" 2>/dev/null || true
    git -C "${RACING_ROOT}" pull --ff-only origin "${REF}" 2>/dev/null || true
    SRC="${RACING_ROOT}"
    SYNC_SOURCE="github_git_pull"
  else
    rm -rf "${RACING_ROOT}.gitclone"
    git clone --depth 1 --branch "${REF}" "${GIT_URL}" "${RACING_ROOT}.gitclone" || {
      echo "git clone failed — set HIBS_RACING_GITHUB_TOKEN or deploy from Mac: ./scripts/deploy_racing_to_vps.sh" >&2
      exit 1
    }
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

chown -R www-data:www-data "${RACING_ROOT}"
systemctl restart hibs-racing 2>/dev/null || true
sleep 3
systemctl is-active hibs-racing 2>/dev/null || echo "WARN: hibs-racing not active yet"

echo ""
curl -fsS --max-time 10 "http://127.0.0.1:5003/api/ping" 2>/dev/null | head -c 200 || true
echo ""
echo "OK: racing synced ref=${REF} at ${STAMP}"

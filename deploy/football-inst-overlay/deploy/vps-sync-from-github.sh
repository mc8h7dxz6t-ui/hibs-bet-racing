#!/usr/bin/env bash
# Institutional VPS code sync from GitHub (no Mac rsync required).
#
# Syncs the full application tree to match a git branch/tag — never touches
# .env, SQLite audit DBs, or .venv (pip install only refreshes deps).
#
# Run on VPS as root:
#   sudo HIBS_SYNC_REF=main bash /opt/hibs-bet/deploy/vps-sync-from-github.sh
#
# Pin a PR branch before merge:
#   sudo HIBS_SYNC_REF=cursor/settlement-ft-backup-scrapers-c6a1 bash ...
#
# After sync, apply the scrape-first institutional profile (API off, scrapers on):
#   sudo bash /opt/hibs-bet/deploy/apply-vps-scrape-first-institutional.sh
#
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-bet}"
REF="${HIBS_SYNC_REF:-main}"
REPO="${HIBS_SYNC_REPO:-mc8h7dxz6t-ui/hibs-bet}"
DOMAIN="${HIBS_DOMAIN:-hibs-bet.co.uk}"
HOST="${DEPLOY_HOST:-$(hostname -f 2>/dev/null || echo vps)}"
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

ARCHIVE_URL="https://github.com/${REPO}/archive/refs/heads/${REF}.tar.gz"
echo "==> fetch ${ARCHIVE_URL}"
curl -fsSL "${ARCHIVE_URL}" | tar -xz -C "${TMP}"

SRC="$(find "${TMP}" -maxdepth 1 -type d -name 'hibs-bet-*' | head -1)"
[[ -n "${SRC}" && -d "${SRC}" ]] || { echo "extract failed — check HIBS_SYNC_REF=${REF}" >&2; exit 1; }

mkdir -p "${APP_ROOT}"
echo "==> rsync ${SRC}/ -> ${APP_ROOT}/ (code only; preserve .env, data, .venv)"
rsync -a \
  --exclude '.git/' \
  --exclude '.env' \
  --exclude '.env.*' \
  --exclude '.venv/' \
  --exclude '.cache/' \
  --exclude 'data/prediction_audit.sqlite' \
  --exclude 'data/prediction_audit_vps.sqlite' \
  --exclude 'data/affiliate_clicks.sqlite' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  "${SRC}/" "${APP_ROOT}/"

cat >"${APP_ROOT}/.deploy-revision" <<EOF
revision=${REF}@github-sync
deployed_at=${STAMP}
deploy_host=${HOST}
domain=${DOMAIN}
service=hibs-bet
sync_source=github_archive
EOF
chown www-data:www-data "${APP_ROOT}/.deploy-revision"

echo "==> pip install (refresh deps; keep existing .venv)"
cd "${APP_ROOT}"
if [[ ! -x .venv/bin/pip ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt

if [[ -f deploy/hibs-bet.service ]]; then
  cp deploy/hibs-bet.service /etc/systemd/system/hibs-bet.service
  systemctl daemon-reload
fi

chown -R www-data:www-data "${APP_ROOT}"
chmod 640 "${APP_ROOT}/.env" 2>/dev/null || true

systemctl restart hibs-bet.service
sleep 4
systemctl is-active hibs-bet.service

echo ""
echo "==> verify"
curl -fsS --max-time 10 "http://127.0.0.1:8000/api/ping" | head -c 400 || true
echo ""
echo ""
echo "OK: synced ref=${REF} at ${STAMP}"
echo "Next: sudo bash ${APP_ROOT}/deploy/apply-vps-scrape-first-institutional.sh"

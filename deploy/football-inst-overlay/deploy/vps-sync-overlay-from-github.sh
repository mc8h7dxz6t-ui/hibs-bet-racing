#!/usr/bin/env bash
# Fetch football-inst-overlay from public GitHub and apply to /opt/hibs-bet.
# No Mac scp required once repo is public.
#
#   sudo HIBS_OVERLAY_REF=main bash /opt/hibs-bet/deploy/vps-sync-overlay-from-github.sh
#   sudo HIBS_OVERLAY_REF=cursor/fix-login-500-b3fc bash ...
#
# One-liner bootstrap (no local scripts needed):
#   curl -fsSL https://raw.githubusercontent.com/mc8h7dxz6t-ui/hibs-bet-racing/main/deploy/football-inst-overlay/deploy/vps-sync-overlay-from-github.sh | \
#     sudo HIBS_OVERLAY_REF=main bash
set -euo pipefail

BET="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
REF="${HIBS_OVERLAY_REF:-main}"
REPO="${HIBS_OVERLAY_REPO:-mc8h7dxz6t-ui/hibs-bet-racing}"
DOMAIN="${HIBS_DOMAIN:-hibs-bet.co.uk}"
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

[[ "$(id -u)" -eq 0 ]] || { echo "run as root: sudo bash $0" >&2; exit 1; }

command -v curl >/dev/null || { echo "curl required" >&2; exit 1; }
command -v tar >/dev/null || { echo "tar required" >&2; exit 1; }
command -v rsync >/dev/null || { echo "rsync required" >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

ARCHIVE_URL="https://github.com/${REPO}/archive/refs/heads/${REF}.tar.gz"
echo "==> fetch ${ARCHIVE_URL}"
curl -fsSL "${ARCHIVE_URL}" | tar -xz -C "${TMP}"

SRC="$(find "${TMP}" -maxdepth 1 -type d -name 'hibs-bet-racing-*' | head -1)"
[[ -n "${SRC}" && -d "${SRC}" ]] || { echo "extract failed — check HIBS_OVERLAY_REF=${REF}" >&2; exit 1; }

OVERLAY="${SRC}/deploy/football-inst-overlay"
[[ -d "${OVERLAY}" ]] || { echo "missing overlay at ${OVERLAY}" >&2; exit 1; }

mkdir -p "${BET}" "${RACING}/deploy"
echo "==> rsync overlay -> ${BET}/"
rsync -a \
  --exclude '.env' \
  --exclude '.venv/' \
  --exclude '.cache/' \
  --exclude 'data/prediction_audit.sqlite' \
  --exclude 'data/prediction_audit_vps.sqlite' \
  "${OVERLAY}/" "${BET}/"

# Keep overlay copy under racing for local re-sync without re-download
rsync -a "${OVERLAY}/" "${RACING}/deploy/football-inst-overlay/"

chmod +x "${BET}/scripts/"*.sh "${BET}/deploy/"*.sh 2>/dev/null || true
mkdir -p "${BET}/.cache" "${BET}/logs" "${BET}/data" /var/log/hibs-bet
chown -R www-data:www-data "${BET}/src" "${BET}/scripts" "${BET}/deploy" "${BET}/templates" "${BET}/.cache" 2>/dev/null || true

cat >"${BET}/.deploy-revision" <<EOF
revision=${REF}@github-overlay
deployed_at=${STAMP}
domain=${DOMAIN}
service=hibs-bet
sync_source=vps-sync-overlay-from-github
EOF
chown www-data:www-data "${BET}/.deploy-revision"

if [[ -f "${BET}/deploy/hibs-bet.service" ]]; then
  cp "${BET}/deploy/hibs-bet.service" /etc/systemd/system/hibs-bet.service
  systemctl daemon-reload
fi

if [[ -x "${BET}/.venv/bin/pip" && -f "${BET}/requirements.txt" ]]; then
  "${BET}/.venv/bin/pip" install -q -r "${BET}/requirements.txt" 2>/dev/null || true
fi

if [[ -f "${BET}/scripts/vps_post_overlay_sync.sh" ]]; then
  echo "==> post-overlay sync"
  DEPLOY_PATH="${BET}" HIBS_RACING_DEPLOY_PATH="${RACING}" bash "${BET}/scripts/vps_post_overlay_sync.sh" || true
fi

systemctl restart hibs-bet 2>/dev/null || true
sleep 3

echo ""
echo "==> verify"
curl -sS -o /dev/null -w 'local_ping=%{http_code}\n' --max-time 10 http://127.0.0.1:8000/api/ping 2>/dev/null || echo "local_ping=000"
if [[ -f "${BET}/scripts/verify_vps_relative_paths.sh" ]]; then
  bash "${BET}/scripts/verify_vps_relative_paths.sh" || true
fi
echo ""
echo "OK: overlay from ${REPO}@${REF} applied to ${BET}"
echo "Next: sudo bash ${BET}/scripts/vps_full_stack_recovery.sh"

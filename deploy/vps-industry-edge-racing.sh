#!/usr/bin/env bash
# Racing industry A+ hooks — execution ledger, SSE, DB integrity.
#
#   sudo bash /opt/hibs-racing/deploy/vps-industry-edge-racing.sh
set -euo pipefail

APP="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
log() { echo "[racing-industry-edge] $*"; }

[[ -d "${APP}" ]] || { echo "missing ${APP}"; exit 1; }

if [[ -f "${APP}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${APP}/.env"
  set +a
fi

grep -q '^HIBS_EXEC_INTENT_LEDGER_ENABLED=' "${APP}/.env" 2>/dev/null || \
  echo "HIBS_EXEC_INTENT_LEDGER_ENABLED=1" >>"${APP}/.env"
grep -q '^HIBS_EXEC_INTENT_FSYNC=' "${APP}/.env" 2>/dev/null || \
  echo "HIBS_EXEC_INTENT_FSYNC=1" >>"${APP}/.env"

if [[ -f "${APP}/deploy/repair-feature-store-sqlite.sh" ]]; then
  bash "${APP}/deploy/repair-feature-store-sqlite.sh" --check-only || {
    log "feature_store corrupt — repairing"
    bash "${APP}/deploy/repair-feature-store-sqlite.sh"
  }
fi

if systemctl is-active --quiet hibs-trading-daemon 2>/dev/null; then
  log "trading daemon active (SSE /api/stream/deltas)"
else
  log "trading daemon not running — SSE will show idle until started"
fi

log "racing industry edge hooks complete"

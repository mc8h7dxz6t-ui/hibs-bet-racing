#!/usr/bin/env bash
# Repair empty football fixture bundle on VPS (scrape-first / API-Sports off).
#
#   sudo bash /opt/hibs-bet/scripts/vps_fixture_repair.sh
#   sudo bash /opt/hibs-bet/scripts/vps_fixture_repair.sh --diagnose-only
set -euo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"
DIAG_ONLY=0

for arg in "$@"; do
  [[ "${arg}" == "--diagnose-only" ]] && DIAG_ONLY=1
done

log() { echo "[fixture-repair] $*"; }
warn() { echo "[fixture-repair] WARN: $*" >&2; }

[[ -d "${APP}" ]] || { echo "missing ${APP}" >&2; exit 1; }
mkdir -p "${LOG_DIR}" "${APP}/.cache"
cd "${APP}"

PY="${APP}/.venv/bin/python3"
[[ -x "${PY}" ]] || { echo "missing ${PY} — create venv first" >&2; exit 1; }

# Ensure cache always lands under app root (root shell often lacks HIBS_CACHE_DIR).
touch "${APP}/.env"
grep -q '^HIBS_CACHE_DIR=' "${APP}/.env" 2>/dev/null || \
  echo 'HIBS_CACHE_DIR=/opt/hibs-bet/.cache' >>"${APP}/.env"
grep -q '^HOME=' "${APP}/.env" 2>/dev/null || echo 'HOME=/opt/hibs-bet' >>"${APP}/.env"

export HOME="${APP}"
export DEPLOY_PATH="${APP}"
export PYTHONPATH="${APP}/src"
export HIBS_PRODUCTION=1
export HIBS_CACHE_DIR="${HIBS_CACHE_DIR:-${APP}/.cache}"
export LOG_DIR="${LOG_DIR}"

log "diagnose (before)"
"${PY}" "${APP}/scripts/diagnose_fixtures_vps.py" || true

if [[ "${DIAG_ONLY}" -eq 1 ]]; then
  exit 0
fi

log "apply scrape-first institutional profile (idempotent)"
if [[ -f "${APP}/deploy/apply-vps-scrape-first-institutional.sh" ]]; then
  bash "${APP}/deploy/apply-vps-scrape-first-institutional.sh" || warn "scrape-first apply failed"
fi

log "fixture warm (force refresh)"
HIBS_FIXTURE_WARM_FORCE_REFRESH=1 bash "${APP}/scripts/warm_football_fixtures.sh" \
  >>"${LOG_DIR}/fixture-warm.log" 2>&1 || warn "fixture warm failed"

if [[ -f "${APP}/scripts/warm_low_source_scrape.sh" ]]; then
  log "low-source scrape cycle"
  bash "${APP}/scripts/warm_low_source_scrape.sh" \
    >>"${LOG_DIR}/low-source-scrape.log" 2>&1 || warn "low-source scrape failed"
fi

if [[ -f "${APP}/scripts/data_producer_repair.sh" ]]; then
  log "data producer repair"
  bash "${APP}/scripts/data_producer_repair.sh" >>"${LOG_DIR}/fixture-repair.log" 2>&1 || true
fi

log "diagnose (after)"
if ! "${PY}" "${APP}/scripts/diagnose_fixtures_vps.py"; then
  warn "still 0 fixtures — check FOOTBALL_DATA_ORG_KEY, FotMob/ESPN reachability, logs"
  exit 2
fi

log "restart hibs-bet"
systemctl restart hibs-bet 2>/dev/null || true
sleep 3
log "done — tail ${LOG_DIR}/fixture-warm.log if dashboard still empty"

#!/usr/bin/env bash
# Bootstrap racing data after VPS sync — results ingest, horse form, card warm.
#
#   sudo bash /opt/hibs-racing/scripts/vps_racing_data_bootstrap.sh
set -euo pipefail

APP="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
BET="${HIBS_BET_DEPLOY_PATH:-/opt/hibs-bet}"
LOOKBACK="${HIBS_LOOKBACK_DAYS:-30}"
SINCE="${HIBS_HORSE_STATE_SINCE:-2024-07-01}"
PY="${APP}/.venv/bin/python3"
CLI="${APP}/.venv/bin/hibs-racing"

log() { echo "[racing-bootstrap] $*"; }

[[ -x "${PY}" ]] || { log "ERROR: missing ${PY}"; exit 1; }

mkdir -p "${APP}/.cache/pip" "${APP}/data/.cache"
chown -R www-data:www-data "${APP}/.cache" 2>/dev/null || true

_run_as_www() {
  sudo -u www-data env \
    HOME="${APP}" PYTHONPATH="${APP}/src" \
    PIP_CACHE_DIR="${APP}/.cache/pip" \
    HIBS_RACING_CACHE_DIR="${APP}/data/.cache" \
    "$@"
}

log "1/5 service check"
if systemctl is-enabled hibs-racing &>/dev/null; then
  systemctl is-active hibs-racing || systemctl restart hibs-racing
  sleep 2
fi

log "2/5 ingest raceform + scrape results (lookback=${LOOKBACK}d)"
RFDB="${APP}/data/raceform.db"
if [[ -f "${RFDB}" ]]; then
  _run_as_www "${CLI}" ingest-raceform "${RFDB}" --since "$(date -u -d "-${LOOKBACK} days" +%F)" --sync || \
    log "WARN: ingest-raceform partial"
fi
_run_as_www "${CLI}" scrape --days "${LOOKBACK}" --region gb --ingest --from-cache || \
  log "WARN: scrape --from-cache empty — trying live scrape (needs EMAIL/ACCESS_TOKEN)"
_run_as_www "${CLI}" scrape --days "${LOOKBACK}" --region gb --ingest || \
  log "WARN: live scrape failed — add Racing Post creds to ${APP}/.env"

log "3/5 horse_form_state sync (since=${SINCE})"
_run_as_www "${PY}" "${APP}/scripts/sync_horse_form_state.py" --since "${SINCE}"

log "4/5 backfill runner enrich"
_run_as_www "${CLI}" backfill-runner-enrich || log "WARN: enrich backfill partial"

log "5/5 warm cards + thin rescue"
if [[ -f "${APP}/scripts/warm_racing_scrape.sh" ]]; then
  HOME="${APP}" bash "${APP}/scripts/warm_racing_scrape.sh"
elif [[ -f "${BET}/scripts/warm_data_quality_95.sh" ]]; then
  bash "${BET}/scripts/warm_data_quality_95.sh" || true
fi

if [[ -f "${BET}/deploy/lib-racing-unix-socket.sh" ]]; then
  # shellcheck source=/dev/null
  source "${BET}/deploy/lib-racing-unix-socket.sh"
  RC="$(racing_ping_code 12)"
  log "racing unix ping=${RC}"
fi

log "done — verify:"
echo "  ${CLI} stack-probe 2>/dev/null || curl -s --unix-socket /var/run/hibs/racing_execution.sock http://localhost/api/ping"
echo "  ${PY} ${APP}/scripts/measure_dq_cards.py 2>/dev/null || true"

#!/usr/bin/env bash
# One-shot max racing data: multi-region results + odds scrape + settlement.
#
#   sudo bash /opt/hibs-racing/scripts/vps_racing_max_data_now.sh
#
# Env:
#   HIBS_LOOKBACK_DAYS=14   — results scrape window
#   HIBS_DISABLE_ODDSCHECKER=1 — skip OC if VPS IP blocked
set -euo pipefail

APP="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
LOOKBACK="${HIBS_LOOKBACK_DAYS:-14}"
CLI="${APP}/.venv/bin/hibs-racing"
PY="${APP}/.venv/bin/python3"

log() { echo "[racing-max-data] $*"; }
warn() { echo "[racing-max-data] WARN: $*" >&2; }

[[ -x "${CLI}" ]] || { log "ERROR: missing ${CLI}"; exit 1; }
[[ "$(id -u)" -eq 0 ]] || { log "run as root (uses sudo -u www-data)"; exit 1; }

mkdir -p "${APP}/data/.cache" "${APP}/.cache/pip" /var/log/hibs-racing
chown -R www-data:hibs-shared "${APP}/data/.cache" 2>/dev/null || \
  chown -R www-data:www-data "${APP}/data/.cache" "${APP}/.cache" 2>/dev/null || true

_run_as_www() {
  sudo -u www-data env \
    HOME="${APP}" PYTHONPATH="${APP}/src" \
    PIP_CACHE_DIR="${APP}/.cache/pip" \
    HIBS_RACING_CACHE_DIR="${APP}/data/.cache" \
    HIBS_MAX_DATA=1 \
    HIBS_ALWAYS_SCRAPE=1 \
    HIBS_RACING_SCRAPE_FORCE=1 \
    HIBS_ODDS_AUTO_SCRAPE=1 \
    HIBS_ODDSCHECKER_EXCHANGE_ONLY="${HIBS_ODDSCHECKER_EXCHANGE_ONLY:-1}" \
    "$@"
}

log "1/6 live results scrape (gb flat+jump, ire flat) lookback=${LOOKBACK}d"
for spec in "gb flat" "gb jump" "ire flat"; do
  set -- ${spec}
  region="$1"
  rtype="$2"
  _run_as_www "${CLI}" scrape --days "${LOOKBACK}" --region "${region}" --type "${rtype}" --ingest \
    || warn "scrape ${region} ${rtype} partial"
done

log "2/6 settle open paper bets"
_run_as_www "${CLI}" settle-paper | tee /var/log/hibs-racing/settle-paper-max-data.json || warn "settle-paper partial"

log "3/6 refresh cards (gb+ire, 48h window)"
_run_as_www "${CLI}" refresh-cards --source racing_api --window 48 --regions gb,ire \
  || warn "refresh-cards partial"

log "4/6 robust odds scrape (matchbook → betfair → oddschecker exchange)"
if [[ -f "${APP}/scripts/warm_racing_scrape.sh" ]]; then
  HOME="${APP}" HIBS_MAX_DATA=1 HIBS_ALWAYS_SCRAPE=1 HIBS_RACING_SCRAPE_FORCE=1 \
    HIBS_ODDSCHECKER_EXCHANGE_ONLY="${HIBS_ODDSCHECKER_EXCHANGE_ONLY:-1}" \
    bash "${APP}/scripts/warm_racing_scrape.sh" \
    || warn "warm_racing_scrape partial"
fi

log "5/6 horse form + enrich backfill"
if [[ -f "${APP}/scripts/sync_horse_form_state.py" ]]; then
  _run_as_www "${PY}" "${APP}/scripts/sync_horse_form_state.py" --since "$(date -u -d "-${LOOKBACK} days" +%F)" \
    || warn "horse form sync partial"
fi
_run_as_www "${CLI}" backfill-runner-enrich || warn "enrich backfill partial"

log "6/6 DQ probe"
if [[ -f "${APP}/scripts/measure_dq_cards.py" ]]; then
  _run_as_www "${PY}" "${APP}/scripts/measure_dq_cards.py" | tee /var/log/hibs-racing/measure-dq-max-data.json \
    || warn "measure_dq_cards partial"
fi

log "done — check:"
echo "  ${CLI} settle-paper  # should show settled > 0 for stale lanes"
echo "  curl -s --unix-socket /var/run/hibs/racing_execution.sock http://localhost/api/health 2>/dev/null | head"

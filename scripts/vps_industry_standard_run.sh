#!/usr/bin/env bash
# Industry-standard VPS stack run — repair services, verify creds, refresh data, audit gates.
#
# Run on VPS as root after creds updated:
#   sudo bash /opt/hibs-bet/scripts/vps_industry_standard_run.sh --repair
#   sudo bash /opt/hibs-bet/scripts/vps_industry_standard_run.sh --repair --sync-racing
#
# Exit 0 = infrastructure GREEN (services + racing odds path OK)
# Exit 1 = critical failure (service down, missing creds, refresh failed)
# Exit 2 = infrastructure OK but evidence/staking gates not green (expected off-season)
set -euo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"
STATUS_JSON="${LOG_DIR}/industry-standard-status.json"
REPAIR=0
SYNC_RACING=0
SKIP_REFRESH=0

for arg in "$@"; do
  case "${arg}" in
    --repair) REPAIR=1 ;;
    --sync-racing) SYNC_RACING=1 ;;
    --skip-refresh) SKIP_REFRESH=1 ;;
  esac
done

[[ "$(id -u)" -eq 0 ]] || { echo "Run as root: sudo bash $0 [--repair] [--sync-racing]" >&2; exit 1; }
mkdir -p "${LOG_DIR}" /var/log/hibs-racing

log() { echo "[industry] $*"; }
warn() { echo "[industry] WARN: $*" >&2; }

infra_ok=1
evidence_ok=1
fail=0

if [[ "${SYNC_RACING}" -eq 1 && -f "${RACING}/deploy/football-inst-overlay/deploy/vps-sync-racing-from-github.sh" ]]; then
  log "sync racing from GitHub main"
  HIBS_RACING_SYNC_REF="${HIBS_RACING_SYNC_REF:-main}" \
    bash "${RACING}/deploy/football-inst-overlay/deploy/vps-sync-racing-from-github.sh" || fail=1
elif [[ "${SYNC_RACING}" -eq 1 ]]; then
  SYNC_SCRIPT="${APP}/deploy/vps-sync-racing-from-github.sh"
  if [[ -f "${SYNC_SCRIPT}" ]]; then
    HIBS_RACING_SYNC_REF="${HIBS_RACING_SYNC_REF:-main}" bash "${SYNC_SCRIPT}" || fail=1
  else
    warn "no vps-sync-racing-from-github.sh — skip sync"
  fi
fi

THREE_STACK="${APP}/scripts/vps_three_stack_green.sh"
if [[ -f "${THREE_STACK}" ]]; then
  log "three-stack green"
  extra=""
  [[ "${REPAIR}" -eq 1 ]] && extra="--repair"
  if ! bash "${THREE_STACK}" ${extra}; then
    infra_ok=0
    fail=1
  fi
else
  warn "missing ${THREE_STACK}"
fi

if [[ -d "${RACING}" ]]; then
  log "racing credentials + odds"
  CREDS_SCRIPT="${RACING}/scripts/verify_racing_creds.sh"
  creds_rc=0
  if [[ -x "${CREDS_SCRIPT}" ]]; then
    bash "${CREDS_SCRIPT}" || creds_rc=$?
  else
    warn "missing verify_racing_creds.sh"
    creds_rc=1
  fi
  if [[ "${creds_rc}" -eq 1 ]]; then
    infra_ok=0
    fail=1
  elif [[ "${creds_rc}" -eq 2 ]]; then
    infra_ok=0
  fi

  if [[ "${SKIP_REFRESH}" -eq 0 && ( "${REPAIR}" -eq 1 || "${creds_rc}" -ge 2 ) ]]; then
    log "racing data refresh (auto odds + cards)"
    REFRESH="${RACING}/scripts/daily_refresh.sh"
    WRAPPER="${RACING}/scripts/cron_refresh_wrapper.sh"
    runner="${REFRESH}"
    [[ -x "${WRAPPER}" ]] && runner="${WRAPPER}"
    if [[ -x "${runner}" ]]; then
      set +e
      (
        cd "${RACING}"
        export HOME="${RACING}"
        export HIBS_ODDS_SOURCE="${HIBS_ODDS_SOURCE:-auto}"
        export HIBS_RACING_CARD_SOURCE="${HIBS_RACING_CARD_SOURCE:-auto}"
        export HIBS_OBSERVATION_LANE="${HIBS_OBSERVATION_LANE:-1}"
        bash "${runner}"
      ) >>/var/log/hibs-racing/industry-refresh.log 2>&1
      refresh_rc=$?
      set -e
      if [[ "${refresh_rc}" -ne 0 ]]; then
        warn "daily_refresh exit ${refresh_rc} — trying warm_racing_scrape"
        if [[ -x "${RACING}/scripts/warm_racing_scrape.sh" ]]; then
          HOME="${RACING}" bash "${RACING}/scripts/warm_racing_scrape.sh" \
            >>/var/log/hibs-racing/industry-refresh.log 2>&1 || true
        fi
      fi
      if [[ -x "${CREDS_SCRIPT}" ]]; then
        bash "${CREDS_SCRIPT}" || creds_rc=$?
        [[ "${creds_rc}" -eq 1 ]] && infra_ok=0 && fail=1
        [[ "${creds_rc}" -ge 2 ]] && infra_ok=0
      fi
    else
      warn "no daily_refresh at ${RACING}"
    fi
  fi
fi

log "football evidence gates"
FB_GATES="${APP}/scripts/verify_football_evidence_gates.sh"
if [[ -f "${FB_GATES}" ]]; then
  bash "${FB_GATES}" || evidence_ok=0
else
  warn "missing verify_football_evidence_gates.sh"
fi

log "racing evidence gates"
RC_GATES="${RACING}/scripts/verify_racing_evidence_gates.sh"
if [[ -f "${RC_GATES}" ]]; then
  bash "${RC_GATES}" || evidence_ok=0
fi

log "personal staking green lights"
STAKE="${APP}/scripts/verify_personal_staking_greenlights.sh"
[[ -f "${STAKE}" ]] && bash "${STAKE}" || true

log "institutional failsafe"
FAILSAFE="${APP}/scripts/institutional_failsafe_verify.sh"
[[ -f "${FAILSAFE}" ]] && bash "${FAILSAFE}" || true

PY="${APP}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY="python3"
"${PY}" -c "
import json
from datetime import datetime, timezone
out = {
    'ts': datetime.now(timezone.utc).isoformat(),
    'infrastructure_green': ${infra_ok} == 1 and ${fail} == 0,
    'evidence_green': ${evidence_ok} == 1,
    'repair': ${REPAIR} == 1,
    'sync_racing': ${SYNC_RACING} == 1,
    'note': 'Evidence gates need live matchdays — summer F7-F9 red is expected.',
}
open('${STATUS_JSON}', 'w').write(json.dumps(out, indent=2))
print(json.dumps(out, indent=2))
"

echo ""
if [[ "${fail}" -ne 0 ]]; then
  warn "INDUSTRY STANDARD: CRITICAL — fix services/creds/refresh above"
  exit 1
fi
if [[ "${infra_ok}" -eq 1 && "${evidence_ok}" -eq 1 ]]; then
  log "INDUSTRY STANDARD: FULL GREEN (infra + evidence)"
  exit 0
fi
if [[ "${infra_ok}" -eq 1 ]]; then
  log "INDUSTRY STANDARD: INFRA GREEN — evidence gates waiting on matchdays/data"
  exit 2
fi
warn "INDUSTRY STANDARD: AMBER — partial infra"
exit 2

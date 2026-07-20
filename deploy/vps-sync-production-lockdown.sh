#!/usr/bin/env bash
# Sync production lockdown code into flat /opt/hibs-racing tree (no git checkout).
#
#   sudo REPO_ROOT=/path/to/hibs-bet-racing bash deploy/vps-sync-production-lockdown.sh
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-racing}"
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

log() { echo "[vps-sync-lockdown] $*"; }
warn() { echo "[vps-sync-lockdown] WARN: $*" >&2; }

[[ "$(id -u)" -ne 0 ]] && { echo "Run as root" >&2; exit 1; }
[[ -d "${REPO_ROOT}/src/hibs_racing" ]] || { echo "REPO_ROOT invalid: ${REPO_ROOT}" >&2; exit 1; }

log "source ${REPO_ROOT} → ${APP_ROOT}"

rsync -a \
  "${REPO_ROOT}/src/hibs_racing/web.py" \
  "${REPO_ROOT}/src/hibs_racing/cli.py" \
  "${APP_ROOT}/src/hibs_racing/"

rsync -a \
  "${REPO_ROOT}/src/hibs_racing/cards/score_card.py" \
  "${APP_ROOT}/src/hibs_racing/cards/"

rsync -a \
  "${REPO_ROOT}/src/hibs_racing/portfolio/" \
  "${APP_ROOT}/src/hibs_racing/portfolio/"

rsync -a \
  "${REPO_ROOT}/src/hibs_racing/place/exchange_config.py" \
  "${REPO_ROOT}/src/hibs_racing/place/exchange_status.py" \
  "${REPO_ROOT}/src/hibs_racing/place/kelly.py" \
  "${REPO_ROOT}/src/hibs_racing/place/portfolio_kelly.py" \
  "${APP_ROOT}/src/hibs_racing/place/" 2>/dev/null || true

if [[ -f "${REPO_ROOT}/src/hibs_racing/place/ew_ev.py" ]]; then
  rsync -a "${REPO_ROOT}/src/hibs_racing/place/ew_ev.py" "${APP_ROOT}/src/hibs_racing/place/"
fi

rsync -a \
  "${REPO_ROOT}/deploy/apply-vps-exchange-ev.sh" \
  "${REPO_ROOT}/deploy/vps-drop-exchange-ev-modules.sh" \
  "${REPO_ROOT}/deploy/vps-sync-production-lockdown.sh" \
  "${APP_ROOT}/deploy/"
mkdir -p "${APP_ROOT}/scripts"
[[ -f "${REPO_ROOT}/scripts/verify_exchange_ev_shadow.sh" ]] && \
  rsync -a "${REPO_ROOT}/scripts/verify_exchange_ev_shadow.sh" "${APP_ROOT}/scripts/"

if [[ -f "${APP_ROOT}/deploy/vps-drop-exchange-ev-modules.sh" ]]; then
  log "exchange-ev module drop-in (idempotent)"
  bash "${APP_ROOT}/deploy/vps-drop-exchange-ev-modules.sh" || warn "drop-in partial"
fi

if [[ -f "${APP_ROOT}/deploy/apply-vps-exchange-ev.sh" ]]; then
  bash "${APP_ROOT}/deploy/apply-vps-exchange-ev.sh"
fi

if [[ -x "${APP_ROOT}/.venv/bin/pip" ]]; then
  log "pip install -e (quiet)"
  sudo -u www-data env HOME="${APP_ROOT}" \
    "${APP_ROOT}/.venv/bin/pip" install -q -e "${APP_ROOT}" 2>/dev/null || \
    warn "pip install -e failed — check venv"
fi

import_smoke() {
  sudo -u www-data env HOME="${APP_ROOT}" PYTHONPATH=src \
    "${APP_ROOT}/.venv/bin/python3" -c "
from hibs_racing.portfolio.ledger_summary import build_ledger_summary_payload
from hibs_racing.web import create_app
app = create_app()
assert app is not None
print('import ok', build_ledger_summary_payload().get('status'))
"
}
import_smoke || warn "import smoke failed"

chown -R www-data:www-data "${APP_ROOT}/src" 2>/dev/null || true
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) lockdown-sync $(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || echo local)" \
  >>"${APP_ROOT}/.deploy-revision" 2>/dev/null || true

log "sync complete"

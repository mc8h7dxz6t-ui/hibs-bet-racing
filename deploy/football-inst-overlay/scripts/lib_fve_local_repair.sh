#!/usr/bin/env bash
# Idempotent repair for local FVE / line-shopper Docker on the main VPS (127.0.0.1:8010).
#
#   sudo bash /opt/hibs-bet/scripts/lib_fve_local_repair.sh
set -uo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
FVE_ROOT="${FVE_DEPLOY_PATH:-/opt/fve}"
FVE_PORT="${FVE_API_PORT:-8010}"
PUBLIC="${HIBS_PUBLIC_HOST:-hibs-bet.co.uk}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"

log() { echo "[fve-repair] $*"; }
warn() { echo "[fve-repair] WARN: $*" >&2; }

[[ "$(id -u)" -eq 0 ]] || { warn "run as root"; exit 0; }

if [[ -f "${APP}/scripts/lib_stack_host.sh" ]]; then
  # shellcheck source=lib_stack_host.sh
  source "${APP}/scripts/lib_stack_host.sh"
  stack_load_env
else
  FVE_HOST="127.0.0.1"
  STACK_FVE_LOCAL=1
fi

if [[ "${STACK_FVE_LOCAL:-0}" -ne 1 ]]; then
  log "skip — FVE host ${FVE_HOST} is remote (not local Docker repair)"
  exit 0
fi

mkdir -p "${LOG_DIR}" /var/lib/fve/scrape-lines /var/log/fve

fve_health_ok() {
  curl -fsS --max-time 8 "http://127.0.0.1:${FVE_PORT}/health" 2>/dev/null | \
    python3 -c "
import json, sys
d = json.load(sys.stdin)
w = d.get('worker') or {}
sys.exit(0 if not d.get('paused') and w.get('alive') else 1)
" 2>/dev/null
}

fixture_count() {
  curl -fsS --max-time 12 "http://127.0.0.1:8000/api/fve/fixtures" 2>/dev/null | \
    python3 -c "import json,sys; d=json.load(sys.stdin); print(int(d.get('count') or 0))" 2>/dev/null || echo 0
}

log "ensure FVE tree + line-trader wiring"
if [[ ! -f "${FVE_ROOT}/docker-compose.yml" && -f "${APP}/deploy/apply-vps-fve-line-trader.sh" ]]; then
  HIBS_PUBLIC_HOST="${PUBLIC}" DEPLOY_PATH="${APP}" FVE_DEPLOY_PATH="${FVE_ROOT}" \
    bash "${APP}/deploy/apply-vps-fve-line-trader.sh" || warn "apply-vps-fve-line-trader failed"
elif [[ -f "${APP}/deploy/vps-install-fve-upstream.sh" ]]; then
  bash "${APP}/deploy/vps-install-fve-upstream.sh" || true
fi

if [[ -f "${FVE_ROOT}/.env" ]]; then
  if ! grep -q '^HIBS_UPSTREAM_BASE_URL=' "${FVE_ROOT}/.env" 2>/dev/null; then
    echo "HIBS_UPSTREAM_BASE_URL=http://127.0.0.1:8000" >>"${FVE_ROOT}/.env"
  fi
  # Prefer local football during repair (DNS-independent).
  sed -i 's|^HIBS_UPSTREAM_BASE_URL=.*|HIBS_UPSTREAM_BASE_URL=http://127.0.0.1:8000|' "${FVE_ROOT}/.env" 2>/dev/null || true
fi

if [[ -f "${FVE_ROOT}/docker-compose.yml" ]] && command -v docker >/dev/null 2>&1; then
  log "docker compose up (redis api worker)"
  (cd "${FVE_ROOT}" && COMPOSE_PROFILES=ingest FVE_API_PORT="${FVE_PORT}" \
    docker compose up -d --build redis api worker) 2>>"${LOG_DIR}/fve-repair.log" || \
    warn "docker compose failed — see ${LOG_DIR}/fve-repair.log"
fi

fc="$(fixture_count)"
if [[ "${fc}" -lt 1 && -f "${APP}/.venv/bin/python3" ]]; then
  log "warm football fixture cache (count=${fc})"
  PYTHONPATH="${APP}/src" HOME="${APP}" "${APP}/.venv/bin/python3" -c "
from hibs_predictor.web import fetch_all_fixtures
b = fetch_all_fixtures(force_refresh=True, attach_live=True, allow_stale=True)
print('loaded', len(b.get('all') or []))
" >>"${LOG_DIR}/fve-repair.log" 2>&1 || warn "fixture warm failed"
fi

if ! fve_health_ok; then
  log "FVE worker not alive — recycle worker container"
  if [[ -f "${FVE_ROOT}/docker-compose.yml" ]]; then
    (cd "${FVE_ROOT}" && COMPOSE_PROFILES=ingest docker compose restart worker api) \
      >>"${LOG_DIR}/fve-repair.log" 2>&1 || true
    sleep 6
  fi
fi

if [[ -f "${FVE_ROOT}/scripts/fve_hibs_lines_collector.py" ]]; then
  log "lines collector --from-watchlist"
  if [[ -f "${FVE_ROOT}/docker-compose.yml" ]] && docker compose -f "${FVE_ROOT}/docker-compose.yml" ps worker 2>/dev/null | grep -q Up; then
    docker compose -f "${FVE_ROOT}/docker-compose.yml" exec -T worker \
      python scripts/fve_hibs_lines_collector.py --from-watchlist \
      >>"${LOG_DIR}/fve-repair.log" 2>&1 || true
  else
    (cd "${FVE_ROOT}" && HIBS_UPSTREAM_BASE_URL=http://127.0.0.1:8000 \
      FVE_SCRAPE_LINES_DIR=/var/lib/fve/scrape-lines \
      python3 scripts/fve_hibs_lines_collector.py --from-watchlist) \
      >>"${LOG_DIR}/fve-repair.log" 2>&1 || true
  fi
fi

if [[ -f "${APP}/deploy/apply-nginx-fve-line-trader.sh" ]] && command -v nginx >/dev/null 2>&1; then
  HIBS_PUBLIC_HOST="${PUBLIC}" DEPLOY_PATH="${APP}" FVE_API_PORT="${FVE_PORT}" \
    bash "${APP}/deploy/apply-nginx-fve-line-trader.sh" >>"${LOG_DIR}/fve-repair.log" 2>&1 || true
  systemctl reload nginx 2>/dev/null || true
fi

if fve_health_ok; then
  log "FVE local GREEN"
  exit 0
fi

warn "FVE still not green — tail ${LOG_DIR}/fve-repair.log"
exit 0

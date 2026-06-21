#!/usr/bin/env bash
# VPS: FVE line-trader stack (scrape-heavy, hibs upstream) on :8010 — no API key burn on FVE.
#
#   sudo bash /opt/hibs-bet/deploy/apply-vps-fve-line-trader.sh
#
# Prereqs: hibs-bet at /opt/hibs-bet; football-app (FVE) at FVE_DEPLOY_PATH (default /opt/fve).
set -euo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
FVE_ROOT="${FVE_DEPLOY_PATH:-/opt/fve}"
HIBS_URL="${HIBS_UPSTREAM_BASE_URL:-https://hibs-bet.co.uk}"
PUBLIC_HOST="${HIBS_PUBLIC_HOST:-hibs-bet.co.uk}"
SCRAPE_DIR="${FVE_SCRAPE_LINES_DIR:-/var/lib/fve/scrape-lines}"
FVE_PORT="${FVE_API_PORT:-8010}"
BRANCH="${HIBS_FVE_RAW_BRANCH:-main}"
RAW="https://raw.githubusercontent.com/mc8h7dxz6t-ui/football-app/${BRANCH}"

log() { echo "[fve-line-trader] $*"; }

read_env_val() {
  local key="$1" file="$2"
  grep -E "^${key}=" "${file}" 2>/dev/null | tail -1 | cut -d= -f2- || true
}

log "1/6 — hibs-bet FVE upstream proxy"
bash "${APP}/deploy/vps-install-fve-upstream.sh"

LINES_TOKEN="$(read_env_val FVE_LINES_TOKEN "${APP}/.env")"

log "2/6 — ensure FVE tree at ${FVE_ROOT}"
if [[ ! -f "${FVE_ROOT}/docker-compose.yml" ]]; then
  if [[ -d "${APP}/../football-app" && -f "${APP}/../football-app/docker-compose.yml" ]]; then
    FVE_ROOT="$(cd "${APP}/../football-app" && pwd)"
  else
    mkdir -p "${FVE_ROOT}"
    if command -v git >/dev/null 2>&1; then
      git clone --depth 1 "https://github.com/mc8h7dxz6t-ui/football-app.git" "${FVE_ROOT}/.src" 2>/dev/null || true
      if [[ -f "${FVE_ROOT}/.src/docker-compose.yml" ]]; then
        rsync -a "${FVE_ROOT}/.src/" "${FVE_ROOT}/"
      fi
    fi
  fi
fi

log "3/6 — scrape lines dir + FVE .env"
mkdir -p "${SCRAPE_DIR}" /var/log/fve
touch "${FVE_ROOT}/.env"
upsert() {
  local key="$1" val="$2"
  if grep -q "^${key}=" "${FVE_ROOT}/.env" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" "${FVE_ROOT}/.env"
  else
    echo "${key}=${val}" >> "${FVE_ROOT}/.env"
  fi
}
upsert FVE_PAUSED 0
upsert FVE_FEED_MODE scrape
upsert FVE_SCRAPE_HEAVY 1
upsert FVE_SCRAPE_LINES_DIR "${SCRAPE_DIR}"
upsert HIBS_UPSTREAM_BASE_URL "${HIBS_URL}"
upsert FVE_AUTO_WATCHLIST 1
upsert FVE_API_PORT "${FVE_PORT}"
upsert FVE_WS_DELTA_UPDATES 1
if [[ -n "${LINES_TOKEN}" ]]; then
  upsert HIBS_UPSTREAM_TOKEN "${LINES_TOKEN}"
fi

touch "${APP}/.env"
hibs_upsert() {
  local key="$1" val="$2"
  if grep -q "^${key}=" "${APP}/.env" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" "${APP}/.env"
  else
    echo "${key}=${val}" >> "${APP}/.env"
  fi
}
hibs_upsert HIBS_FVE_PUBLIC_API_URL "https://${PUBLIC_HOST}/fve-api"
hibs_upsert HIBS_FVE_PUBLIC_WS_URL "wss://${PUBLIC_HOST}/fve-api"
hibs_upsert FVE_API_URL "http://127.0.0.1:${FVE_PORT}"

log "4/6 — lines collector cron (5 min)"
TOKEN_ENV=""
if [[ -n "${LINES_TOKEN}" ]]; then
  TOKEN_ENV="HIBS_UPSTREAM_TOKEN=${LINES_TOKEN}"
fi
CRON_LINE="*/5 * * * * cd ${FVE_ROOT} && HIBS_UPSTREAM_BASE_URL=${HIBS_URL} FVE_SCRAPE_LINES_DIR=${SCRAPE_DIR} ${TOKEN_ENV} /usr/bin/python3 scripts/fve_hibs_lines_collector.py --from-watchlist >> /var/log/fve/lines-collector.log 2>&1"
( crontab -l 2>/dev/null | grep -v 'fve_hibs_lines_collector' || true; echo "${CRON_LINE}" ) | crontab -

log "5/6 — start FVE API + ingest worker (docker profile ingest)"
if [[ -f "${FVE_ROOT}/docker-compose.yml" ]]; then
  (cd "${FVE_ROOT}" && FVE_API_PORT="${FVE_PORT}" COMPOSE_PROFILES=ingest docker compose up -d --build redis api worker) || \
    log "WARN docker compose failed — run: cd ${FVE_ROOT} && COMPOSE_PROFILES=ingest docker compose up -d --build redis api worker"
else
  log "WARN no docker-compose.yml — curl bootstrap from football-app:"
  echo "  curl -fsSL ${RAW}/scripts/vps_unpause_fve_scrape_stack.sh | sudo bash"
fi

if [[ -f "${FVE_ROOT}/scripts/fve_hibs_lines_collector.py" ]]; then
  (cd "${FVE_ROOT}" && HIBS_UPSTREAM_BASE_URL="${HIBS_URL}" FVE_SCRAPE_LINES_DIR="${SCRAPE_DIR}" ${TOKEN_ENV} \
    python3 scripts/fve_hibs_lines_collector.py --from-watchlist) || true
fi

log "6/6 — nginx /fve-api proxy (when nginx present)"
if command -v nginx >/dev/null 2>&1 && [[ -x "${APP}/deploy/apply-nginx-fve-line-trader.sh" ]]; then
  HIBS_PUBLIC_HOST="${PUBLIC_HOST}" DEPLOY_PATH="${APP}" FVE_API_PORT="${FVE_PORT}" \
    bash "${APP}/deploy/apply-nginx-fve-line-trader.sh" || log "WARN nginx apply skipped"
  systemctl restart hibs-bet 2>/dev/null || true
else
  log "INFO set manually: HIBS_FVE_PUBLIC_WS_URL=wss://${PUBLIC_HOST}/fve-api"
fi

log "verify:"
echo "  curl -sS http://127.0.0.1:8000/api/fve/status?full=1 | python3 -m json.tool | head -24"
echo "  curl -sS http://127.0.0.1:${FVE_PORT}/health | python3 -m json.tool | head -24"
echo "  curl -sS http://127.0.0.1:8000/api/fve/fixtures | python3 -m json.tool | head -12"
echo "  open https://${PUBLIC_HOST}/line-trader"

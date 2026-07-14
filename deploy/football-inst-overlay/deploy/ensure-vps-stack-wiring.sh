#!/usr/bin/env bash
# Idempotent VPS wiring: .env dedupe, FVE proxy, probe flags, stack health log.
#
#   sudo bash /opt/hibs-bet/deploy/ensure-vps-stack-wiring.sh
#   sudo bash /opt/hibs-bet/deploy/ensure-vps-stack-wiring.sh --repair
set -euo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
STACK_ENV="${HIBS_STACK_ENV:-/etc/hibs-bet/stack.env}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"
REPAIR=0

for arg in "$@"; do
  [[ "${arg}" == "--repair" ]] && REPAIR=1
done

log() { echo "[stack-wiring] $*"; }
warn() { echo "[stack-wiring] WARN: $*" >&2; }

[[ "$(id -u)" -eq 0 ]] || { echo "run as root" >&2; exit 1; }
mkdir -p "${LOG_DIR}" /etc/hibs-bet
# shellcheck source=lib_env_upsert.sh
source "${APP}/deploy/lib_env_upsert.sh"

FVE_HOST="${FVE_REMOTE_HOST:-}"
PUBLIC="${HIBS_PUBLIC_HOST:-hibs-bet.co.uk}"
if [[ -f "${STACK_ENV}" ]]; then
  # shellcheck disable=SC1090
  source "${STACK_ENV}"
  FVE_HOST="${FVE_REMOTE_HOST:-${FVE_HOST}}"
  PUBLIC="${HIBS_PUBLIC_HOST:-${PUBLIC}}"
fi
FVE_HOST="${FVE_HOST:-77.68.89.75}"
FVE_PORT="${FVE_API_PORT:-8010}"

touch "${APP}/.env"
env_dedupe_file "${APP}/.env"

DEPLOY_DATE="$(grep '^HIBS_EVIDENCE_DEPLOY_DATE=' "${APP}/.env" 2>/dev/null | tail -1 | cut -d= -f2-)"
[[ -n "${DEPLOY_DATE}" ]] || DEPLOY_DATE="$(date -u +%Y-%m-%d)"

env_ensure_keys "${APP}/.env" \
  FVE_API_URL "http://${FVE_HOST}:${FVE_PORT}" \
  HIBS_FVE_INTEGRATION 1 \
  HIBS_HEALTH_INPLAY_PROBE 1 \
  HIBS_HEALTH_RACING_PROBE 1 \
  HIBS_RACING_EVIDENCE_LOCAL 1 \
  HIBS_AUTH_PUBLIC_HEALTH 1 \
  HIBS_EVIDENCE_DEPLOY_DATE "${DEPLOY_DATE}"

chown www-data:www-data "${APP}/.env" 2>/dev/null || true

NGINX_SITE="/etc/nginx/sites-available/hibs-bet"
FVE_PROXY_OK=0
if [[ -f "${NGINX_SITE}" ]] && grep -qE 'fve-api proxy begin|hibs-fve-api-begin' "${NGINX_SITE}" 2>/dev/null; then
  FVE_PROXY_OK=1
fi

STACK_FVE_LOCAL=0
case "${FVE_HOST}" in
  127.0.0.1|localhost|::1) STACK_FVE_LOCAL=1 ;;
esac

if [[ "${FVE_PROXY_OK}" -eq 0 && "${REPAIR}" -eq 1 ]]; then
  if [[ "${STACK_FVE_LOCAL}" -eq 1 && -f "${APP}/deploy/apply-vps-fve-line-trader.sh" ]]; then
    log "repair: local FVE line-trader + nginx"
    HIBS_PUBLIC_HOST="${PUBLIC}" DEPLOY_PATH="${APP}" \
      bash "${APP}/deploy/apply-vps-fve-line-trader.sh" || warn "FVE line-trader apply failed"
  elif [[ -f "${APP}/deploy/apply-vps-fve-remote-host.sh" ]]; then
    log "repair: nginx FVE proxy missing — apply-vps-fve-remote-host"
    FVE_REMOTE_HOST="${FVE_HOST}" DEPLOY_PATH="${APP}" HIBS_PUBLIC_HOST="${PUBLIC}" \
      bash "${APP}/deploy/apply-vps-fve-remote-host.sh" || warn "FVE proxy apply failed"
  fi
  if [[ -f "${NGINX_SITE}" ]] && grep -qE 'fve-api proxy begin|hibs-fve-api-begin' "${NGINX_SITE}" 2>/dev/null; then
    FVE_PROXY_OK=1
  fi
fi

FVE_HEALTH=0
if curl -fsS --max-time 8 "http://${FVE_HOST}:${FVE_PORT}/health" >/dev/null 2>&1; then
  FVE_HEALTH=1
fi

if [[ "${FVE_HEALTH}" -eq 0 && "${REPAIR}" -eq 1 && "${STACK_FVE_LOCAL}" -eq 1 && -f "${APP}/scripts/lib_fve_local_repair.sh" ]]; then
  log "repair: local FVE Docker worker"
  bash "${APP}/scripts/lib_fve_local_repair.sh" || warn "local FVE repair issues"
  if curl -fsS --max-time 8 "http://${FVE_HOST}:${FVE_PORT}/health" >/dev/null 2>&1; then
    FVE_HEALTH=1
  fi
fi

RACING_PING=0
if curl -fsS --max-time 8 "http://127.0.0.1:5003/api/ping" >/dev/null 2>&1; then
  RACING_PING=1
elif curl -fsS --max-time 12 "https://${PUBLIC}/racing/api/ping" >/dev/null 2>&1; then
  RACING_PING=1
fi

FOOTBALL_PING=0
curl -fsS --max-time 8 "http://127.0.0.1:8000/api/ping" >/dev/null 2>&1 && FOOTBALL_PING=1

FOOTBALL_HEALTH_LIGHT=0
FOOTBALL_HEALTH_MS=""
if curl -fsS --max-time 12 "http://127.0.0.1:8000/api/health?light=1" -o /tmp/hibs_health_light.json 2>/dev/null; then
  FOOTBALL_HEALTH_LIGHT=1
  FOOTBALL_HEALTH_MS="$(python3 -c "import json; print(json.load(open('/tmp/hibs_health_light.json')).get('data_producer',{}).get('ok',''))" 2>/dev/null || true)"
fi

DATA_PROD_OK=0
if [[ -f "${APP}/src/hibs_predictor/data_producer_slo.py" ]]; then
  if HOME="${APP}" PYTHONPATH="${APP}/src" HIBS_PRODUCTION=1 python3 -c "
from hibs_predictor.data_producer_slo import build_data_producer_snapshot
import json, sys
s = build_data_producer_snapshot()
print(json.dumps({'ok': s.get('ok'), 'critical_ok': s.get('critical_ok')}))
sys.exit(0 if s.get('ok') else 1)
" >"${LOG_DIR}/data-producer-slo.json" 2>/dev/null; then
    DATA_PROD_OK=1
  fi
fi

if [[ "${REPAIR}" -eq 1 && "${DATA_PROD_OK}" -eq 0 && -f "${APP}/scripts/data_producer_repair.sh" ]]; then
  SKIP_REPAIR=0
  if HOME="${APP}" PYTHONPATH="${APP}/src" python3 -c "
from hibs_predictor.cache_preservation_policy import disk_bundle_snapshot, should_preserve_disk_bundle
s = disk_bundle_snapshot()
exit(0 if should_preserve_disk_bundle(fixture_count=int(s.get('fixture_count') or 0)) and int(s.get('fixture_count') or 0) > 0 else 1)
" 2>/dev/null; then
    if [[ "${FOOTBALL_PING}" -eq 0 && "${FOOTBALL_HEALTH_LIGHT}" -eq 0 ]]; then
      log "repair: data producer red but disk bundle preserved — service restart only"
      systemctl restart hibs-bet 2>/dev/null || true
      SKIP_REPAIR=1
    fi
  fi
  if [[ "${SKIP_REPAIR}" -eq 0 ]]; then
    log "repair: data producer SLO red"
    bash "${APP}/scripts/data_producer_repair.sh" || warn "data producer repair issues"
  fi
fi

TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat >"${LOG_DIR}/stack-wiring.json" <<EOF
{"ts":"${TS}","fve_host":"${FVE_HOST}","fve_proxy":${FVE_PROXY_OK},"fve_health":${FVE_HEALTH},"football_ping":${FOOTBALL_PING},"football_health_light":${FOOTBALL_HEALTH_LIGHT},"racing_ping":${RACING_PING},"data_producer_ok":${DATA_PROD_OK}}
EOF

log "fve_proxy=${FVE_PROXY_OK} fve_health=${FVE_HEALTH} football=${FOOTBALL_PING} health_light=${FOOTBALL_HEALTH_LIGHT} racing=${RACING_PING} data_producer=${DATA_PROD_OK}"

if [[ "${RACING_PING}" -eq 0 ]]; then
  warn "racing not reachable — private repo: run ./scripts/deploy_racing_to_vps.sh from Mac once"
fi
if [[ "${FVE_HEALTH}" -eq 0 ]]; then
  warn "FVE health failed at http://${FVE_HOST}:${FVE_PORT}/health"
fi

exit 0

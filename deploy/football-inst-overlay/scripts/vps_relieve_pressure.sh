#!/usr/bin/env bash
# Relieve VPS pressure — lighter crons, fewer workers, scrape/API throttle.
#
#   sudo bash /opt/hibs-bet/scripts/vps_relieve_pressure.sh --apply
#   sudo bash /opt/hibs-bet/scripts/vps_relieve_pressure.sh --restore
#   sudo bash /opt/hibs-bet/scripts/vps_relieve_pressure.sh --apply --stop-racing
#
# Safe during incident response: keeps hibs-bet up, pauses heavy background work.
set -euo pipefail

BET="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"
STATE_DIR="${BET}/.cache/pressure-relief"
ENV_FILE="${BET}/.env"
MARKER="# --- VPS pressure relief (managed by vps_relieve_pressure.sh) ---"
TS="$(date -u +%Y%m%dT%H%M%SZ)"

APPLY=0
RESTORE=0
STOP_RACING=0
for arg in "$@"; do
  case "${arg}" in
    --apply) APPLY=1 ;;
    --restore) RESTORE=1 ;;
    --stop-racing) STOP_RACING=1 ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
  esac
done
[[ "${APPLY}" -eq 1 || "${RESTORE}" -eq 1 ]] || APPLY=1

[[ "$(id -u)" -eq 0 ]] || { echo "run as root: sudo bash $0 --apply" >&2; exit 1; }
[[ -d "${BET}" ]] || { echo "missing ${BET}" >&2; exit 1; }

log() { echo "[pressure-relief] $*"; }

mkdir -p "${STATE_DIR}" "${LOG_DIR}"

strip_pressure_env() {
  [[ -f "${ENV_FILE}" ]] || return 0
  if ! grep -qF "${MARKER}" "${ENV_FILE}" 2>/dev/null; then
    return 0
  fi
  local tmp
  tmp="$(mktemp)"
  awk -v m="${MARKER}" '
    $0 == m { skip=1; next }
    skip && /^HIBS_/ { next }
    skip && /^$/ { skip=0; next }
    skip && /^[^#]/ { skip=0 }
    { print }
  ' "${ENV_FILE}" >"${tmp}"
  mv "${tmp}" "${ENV_FILE}"
}

set_env_kv() {
  local key="$1" val="$2"
  touch "${ENV_FILE}"
  if grep -qE "^${key}=" "${ENV_FILE}" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" "${ENV_FILE}"
  else
    echo "${key}=${val}" >>"${ENV_FILE}"
  fi
}

backup_file() {
  local src="$1" dest="$2"
  [[ -f "${src}" ]] && cp -a "${src}" "${dest}"
}

write_minimal_www_crontab() {
  cat <<EOF
# hibs pressure-relief crontab (${TS}) — minimal background load
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
# Keep site alive only (15m not 5m)
*/15 * * * * sudo bash ${BET}/deploy/cron-hibs-infra-fallback.sh --run >> ${LOG_DIR}/infra-fallback.log 2>&1
# One light audit per day (no force refresh)
35 6 * * * cd ${BET} && HOME=${BET} DEPLOY_PATH=${BET} bash ${BET}/deploy/cron-hibs-calibration.sh --run >> ${LOG_DIR}/daily-audit-am.log 2>&1
EOF
}

write_minimal_root_crontab() {
  local existing filtered
  existing="$(crontab -l 2>/dev/null || true)"
  filtered="$(printf '%s\n' "${existing}" | grep -v '/opt/hibs-bet' | grep -v 'hands-off' | grep -v 'hibs-bet:' | sed '/^$/d' || true)"
  {
    printf '%s\n' "${filtered}"
    echo "# hibs pressure-relief root (${TS}) — hands-off paused"
  }
}

apply_pressure_relief() {
  log "apply (${TS})"
  free -h | head -2 | sed 's/^/  /'

  if crontab -u www-data -l >/dev/null 2>&1; then
    crontab -u www-data -l >"${STATE_DIR}/www-data.crontab.bak.${TS}"
    backup_file "${STATE_DIR}/www-data.crontab.bak.${TS}" "${STATE_DIR}/www-data.crontab.latest"
  fi
  if crontab -l >/dev/null 2>&1; then
    crontab -l >"${STATE_DIR}/root.crontab.bak.${TS}"
    backup_file "${STATE_DIR}/root.crontab.bak.${TS}" "${STATE_DIR}/root.crontab.latest"
  fi

  write_minimal_www_crontab | crontab -u www-data -
  write_minimal_root_crontab | crontab -
  log "installed minimal www-data + root crontabs"

  strip_pressure_env
  cat >>"${ENV_FILE}" <<EOF

${MARKER}
HIBS_PRESSURE_RELIEF=1
HIBS_AUTH_ENABLED=0
HIBS_PROGRESSIVE_LOAD=1
HIBS_DASHBOARD_LITE=1
HIBS_FETCH_DAYS=5
HIBS_FIXTURE_FETCH_WORKERS=1
HIBS_ENRICH_API_SEM=1
HIBS_WARM_FIXTURE_CACHE=0
HIBS_LIVE_SNAPSHOT_ON_LOAD=0
HIBS_LIVE_POLL_SEC=600
HIBS_LOW_SOURCE_AUTO_ENRICH=0
HIBS_LOW_SOURCE_BACKFILL_BUNDLE=0
HIBS_DAILY_AUDIT_FORCE_REFRESH=0
HIBS_SKIP_API_INJURIES=1
HIBS_SKIP_API_SQUAD_DEPTH=1
HIBS_SKIP_API_PLAYER_STATS=1
HIBS_FETCH_FIXTURE_STATISTICS_XG=0
HIBS_ENABLE_PLAYER_INSIGHT=0
HIBS_ENABLE_LINEUP_FETCH=0
EOF
  chown www-data:www-data "${ENV_FILE}" 2>/dev/null || true
  log "appended lite .env block"

  mkdir -p /etc/systemd/system/hibs-bet.service.d
  cat >/etc/systemd/system/hibs-bet.service.d/pressure-relief.conf <<EOF
# Managed by vps_relieve_pressure.sh (${TS})
[Service]
ExecStart=
ExecStart=${BET}/.venv/bin/gunicorn \\
  --workers 1 \\
  --bind 0.0.0.0:8000 \\
  --timeout 180 \\
  --graceful-timeout 30 \\
  --access-logfile - \\
  --error-logfile - \\
  hibs_predictor.web:app
EOF
  backup_file /etc/systemd/system/hibs-bet.service.d/pressure-relief.conf \
    "${STATE_DIR}/hibs-bet-pressure-relief.conf.bak.${TS}"

  log "killing stray warm/scrape jobs"
  pkill -f "warm_football_fixtures" 2>/dev/null || true
  pkill -f "warm_low_source_scrape" 2>/dev/null || true
  pkill -f "run_daily_audit_pipeline" 2>/dev/null || true
  pkill -f "seed_forward_evidence" 2>/dev/null || true

  systemctl daemon-reload
  systemctl restart hibs-bet
  log "hibs-bet restarted (1 gunicorn worker)"

  if [[ "${STOP_RACING}" -eq 1 ]]; then
    systemctl stop hibs-racing 2>/dev/null || true
    log "hibs-racing stopped (--stop-racing)"
  else
    log "hibs-racing left running (use --stop-racing to stop cards stack)"
  fi

  sleep 4
  ping_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 12 http://127.0.0.1:8000/api/ping 2>/dev/null || echo 000)"
  root_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 http://127.0.0.1:8000/ 2>/dev/null || echo 000)"
  echo "ping=${ping_code} root=${root_code}"
  echo ""
  echo "Pressure relief ON:"
  echo "  - crontab: infra fallback 15m + one daily audit only"
  echo "  - gunicorn: 1 worker"
  echo "  - .env: lite dashboard, no scrape enrich, no fixture warm"
  echo "Restore: sudo bash ${BET}/scripts/vps_relieve_pressure.sh --restore"
}

restore_pressure_relief() {
  log "restore"
  strip_pressure_env

  if [[ -f "${STATE_DIR}/www-data.crontab.latest" ]]; then
    crontab -u www-data - <"${STATE_DIR}/www-data.crontab.latest"
    log "restored www-data crontab"
  fi
  if [[ -f "${STATE_DIR}/root.crontab.latest" ]]; then
    crontab - <"${STATE_DIR}/root.crontab.latest"
    log "restored root crontab"
  fi

  rm -f /etc/systemd/system/hibs-bet.service.d/pressure-relief.conf
  systemctl daemon-reload
  systemctl restart hibs-bet
  systemctl start hibs-racing 2>/dev/null || true
  chown www-data:www-data "${ENV_FILE}" 2>/dev/null || true
  log "removed gunicorn drop-in; services restarted"
  echo "Restore complete. Re-install full crons if needed:"
  echo "  sudo bash ${BET}/deploy/cron-hibs-ops-automation.sh --install"
}

if [[ "${RESTORE}" -eq 1 ]]; then
  restore_pressure_relief
else
  apply_pressure_relief
fi

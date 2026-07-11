#!/usr/bin/env bash
# Industry-standard football VPS fallback — probe → soft restart → hard recovery → nginx fix.
# Throttled via hibs_predictor.hands_off_guard (non-degrading; cron-safe).
#
#   source /opt/hibs-bet/scripts/lib_football_vps_fallback.sh
#   football_vps_automation_fallback   # returns 0 when localhost green
#
# shellcheck shell=bash

football_vps_fallback_bet="${DEPLOY_PATH:-/opt/hibs-bet}"
football_vps_fallback_racing="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
football_vps_fallback_py="${football_vps_fallback_bet}/.venv/bin/python3"
[[ -x "${football_vps_fallback_py}" ]] || football_vps_fallback_py=python3

football_vps_fallback_log() { echo "[fb-fallback] $*"; }
football_vps_fallback_warn() { echo "[fb-fallback] WARN: $*" >&2; }

football_vps_fallback_allowed() {
  local key="${1:-hibs-bet-fallback}"
  local mins="${2:-45}"
  HOME="${football_vps_fallback_bet}" PYTHONPATH="${football_vps_fallback_bet}/src" \
    "${football_vps_fallback_py}" -c "
from hibs_predictor.hands_off_guard import service_restart_allowed
import sys
sys.exit(0 if service_restart_allowed('${key}', min_minutes=${mins}) else 1)
" 2>/dev/null
}

football_vps_fallback_public_host() {
  local pub="${HIBS_PUBLIC_HOST:-}"
  if [[ -z "${pub}" && -f /etc/hibs-bet/stack.env ]]; then
    # shellcheck disable=SC1091
    source /etc/hibs-bet/stack.env
    pub="${HIBS_PUBLIC_HOST:-}"
  fi
  echo "${pub:-hibs-bet.co.uk}"
}

football_vps_probe() {
  local bet="${1:-${football_vps_fallback_bet}}"
  local pub
  pub="$(football_vps_fallback_public_host)"
  FB_PING="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 8 "http://127.0.0.1:8000/api/ping" 2>/dev/null || echo 000)"
  FB_LOGIN="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "http://127.0.0.1:8000/login" 2>/dev/null || echo 000)"
  FB_PUBLIC_LOGIN="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 12 "https://${pub}/login" 2>/dev/null || echo 000)"
  FB_UNIT="$(systemctl is-active hibs-bet 2>/dev/null || echo inactive)"
  if ss -ltn 2>/dev/null | grep -q ':8000 '; then
    FB_PORT=up
  else
    FB_PORT=down
  fi
  export FB_PING FB_LOGIN FB_PUBLIC_LOGIN FB_UNIT FB_PORT
}

football_vps_soft_restart() {
  football_vps_fallback_log "L1 soft restart hibs-bet"
  systemctl reset-failed hibs-bet 2>/dev/null || true
  systemctl restart hibs-bet 2>/dev/null || true
  sleep 6
}

football_vps_hard_recovery() {
  local bet="${1:-${football_vps_fallback_bet}}"
  if [[ -f "${bet}/scripts/vps_football_hard_recovery.sh" ]]; then
    football_vps_fallback_log "L2 hard recovery"
    DEPLOY_PATH="${bet}" HIBS_RACING_DEPLOY_PATH="${football_vps_fallback_racing}" \
      bash "${bet}/scripts/vps_football_hard_recovery.sh" || return 1
    return 0
  fi
  football_vps_fallback_warn "missing vps_football_hard_recovery.sh"
  return 1
}

football_vps_nginx_fallback() {
  local bet="${1:-${football_vps_fallback_bet}}"
  if [[ ! -f "${bet}/scripts/lib_racing_vps_probe.sh" ]]; then
    return 1
  fi
  # shellcheck source=lib_racing_vps_probe.sh
  source "${bet}/scripts/lib_racing_vps_probe.sh"
  football_vps_fallback_log "L3 nginx upstream repair (localhost OK, public 502)"
  football_vps_fix_nginx_upstream "${bet}" || return 1
  if [[ -f "${bet}/deploy/apply-vps-racing-link.sh" ]]; then
    DEPLOY_PATH="${bet}" HIBS_RACING_DEPLOY_PATH="${football_vps_fallback_racing}" \
      HIBS_PUBLIC_HOST="$(football_vps_fallback_public_host)" \
      bash "${bet}/deploy/apply-vps-racing-link.sh" 2>/dev/null || true
  fi
  return 0
}

# Main entry — industry cascade. Always safe from cron (no exit 1 to parent).
football_vps_automation_fallback() {
  local bet="${1:-${football_vps_fallback_bet}}"
  football_vps_fallback_bet="${bet}"
  if [[ "$(id -u)" -ne 0 ]]; then
    football_vps_fallback_warn "requires root — skip"
    return 0
  fi
  if [[ ! -d "${bet}" ]]; then
    football_vps_fallback_warn "missing ${bet}"
    return 0
  fi

  football_vps_probe "${bet}"
  football_vps_fallback_log "probe unit=${FB_UNIT} port=${FB_PORT} ping=${FB_PING} login=${FB_LOGIN} public=${FB_PUBLIC_LOGIN}"

  if [[ "${FB_PING}" == "200" && "${FB_LOGIN}" =~ ^(200|302)$ ]]; then
    if [[ "${FB_PUBLIC_LOGIN}" =~ ^(200|302)$ ]]; then
      football_vps_fallback_log "GREEN — localhost + public OK"
      return 0
    fi
    if football_vps_fallback_allowed "hibs-bet-nginx" 30; then
      football_vps_nginx_fallback "${bet}" || true
      football_vps_probe "${bet}"
      football_vps_fallback_log "after nginx fix public=${FB_PUBLIC_LOGIN}"
    else
      football_vps_fallback_log "nginx fix throttled (30m)"
    fi
    return 0
  fi

  if [[ "${FB_UNIT}" != "active" ]] && football_vps_fallback_allowed "hibs-bet" 45; then
    football_vps_soft_restart
    football_vps_probe "${bet}"
    football_vps_fallback_log "after soft restart ping=${FB_PING}"
    if [[ "${FB_PING}" == "200" ]]; then
      return 0
    fi
  fi

  if [[ "${FB_PING}" != "200" || "${FB_PORT}" == "down" ]]; then
    if football_vps_fallback_allowed "hibs-bet-hard" 45; then
      football_vps_hard_recovery "${bet}" || true
      football_vps_probe "${bet}"
      football_vps_fallback_log "after hard recovery ping=${FB_PING} login=${FB_LOGIN}"
    else
      football_vps_fallback_log "hard recovery throttled (45m) — ping=${FB_PING}"
    fi
  fi

  if [[ "${FB_PING}" == "200" && ! "${FB_PUBLIC_LOGIN}" =~ ^(200|302)$ ]]; then
    if football_vps_fallback_allowed "hibs-bet-nginx" 30; then
      football_vps_nginx_fallback "${bet}" || true
    fi
  fi

  [[ "${FB_PING}" == "200" ]]
}

racing_vps_automation_fallback() {
  local bet="${1:-${football_vps_fallback_bet}}"
  local racing="${2:-${football_vps_fallback_racing}}"
  local pub ping pub_ping unit
  [[ "$(id -u)" -eq 0 ]] || return 0
  [[ -d "${racing}" ]] || return 0
  pub="$(football_vps_fallback_public_host)"
  ping="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 12 "http://127.0.0.1:5003/api/ping" 2>/dev/null || echo 000)"
  pub_ping="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "https://${pub}/racing/api/ping" 2>/dev/null || echo 000)"
  unit="$(systemctl is-active hibs-racing 2>/dev/null || echo inactive)"
  football_vps_fallback_log "racing probe unit=${unit} local=${ping} public=${pub_ping}"
  if [[ "${ping}" == "200" && "${pub_ping}" == "200" ]]; then
    return 0
  fi
  if [[ "${ping}" == "200" && "${pub_ping}" != "200" ]]; then
    if football_vps_fallback_allowed "hibs-racing-nginx" 30 && [[ -f "${bet}/deploy/apply-vps-racing-link.sh" ]]; then
      football_vps_fallback_log "racing L3 nginx /racing proxy repair"
      DEPLOY_PATH="${bet}" HIBS_RACING_DEPLOY_PATH="${racing}" HIBS_PUBLIC_HOST="${pub}" \
        bash "${bet}/deploy/apply-vps-racing-link.sh" || true
      pub_ping="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "https://${pub}/racing/api/ping" 2>/dev/null || echo 000)"
      [[ "${pub_ping}" == "200" ]] && return 0
    fi
  fi
  if [[ "${ping}" != "200" ]]; then
    if football_vps_fallback_allowed "hibs-racing-hard" 45 && [[ -f "${bet}/scripts/vps_racing_hard_recovery.sh" ]]; then
      football_vps_fallback_log "racing L2 hard recovery"
      HIBS_BET_DEPLOY_PATH="${bet}" HIBS_RACING_DEPLOY_PATH="${racing}" \
        bash "${bet}/scripts/vps_racing_hard_recovery.sh" || true
    fi
  fi
  ping="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 12 "http://127.0.0.1:5003/api/ping" 2>/dev/null || echo 000)"
  [[ "${ping}" == "200" ]]
}

stack_vps_automation_fallback() {
  local bet="${1:-${football_vps_fallback_bet}}"
  local racing="${2:-${football_vps_fallback_racing}}"
  football_vps_automation_fallback "${bet}" || true
  racing_vps_automation_fallback "${bet}" "${racing}" || true
}

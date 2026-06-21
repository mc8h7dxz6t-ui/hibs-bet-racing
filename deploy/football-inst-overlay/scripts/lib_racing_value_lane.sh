#!/usr/bin/env bash
# Shared VPS value-lane repair: score cards, poll Matchbook, fix .env for www-data.
# shellcheck disable=SC2034

racing_value_lane_www_data_exec() {
  local app="$1"
  shift
  local env_file="${app}/.env"
  sudo -u www-data bash -c "
set -a
[[ -f '${env_file}' ]] && source '${env_file}'
set +a
export HOME='${app}' PYTHONPATH=src
cd '${app}'
$*
"
}

racing_value_lane_fix_env() {
  local app="${1:-/opt/hibs-racing}"
  local bet="${2:-/opt/hibs-bet}"
  local env_file="${app}/.env"
  # shellcheck source=lib_matchbook_env.sh
  source "${bet}/scripts/lib_matchbook_env.sh"
  [[ -f "${env_file}" ]] || return 1
  matchbook_load_env "${env_file}"
  local user
  user="$(matchbook_user_value 2>/dev/null || true)"
  if [[ -n "${user}" && -n "${MATCHBOOK_PASSWORD:-}" ]]; then
    grep -qE '^MATCHBOOK_USER=' "${env_file}" || echo "MATCHBOOK_USER=${user}" >>"${env_file}"
    grep -qE '^MATCHBOOK_USERNAME=' "${env_file}" || echo "MATCHBOOK_USERNAME=${user}" >>"${env_file}"
  fi
  chown www-data:www-data "${env_file}" 2>/dev/null || true
  chmod 640 "${env_file}" 2>/dev/null || true
}

racing_value_lane_health_json() {
  curl -fsS --max-time 20 "http://127.0.0.1:5003/api/health" 2>/dev/null || echo '{}'
}

racing_value_lane_needs_repair() {
  local body="${1:-$(racing_value_lane_health_json)}"
  python3 -c "
import json, sys
from datetime import datetime, timezone
try:
    h = json.loads(sys.stdin.read() or '{}')
except json.JSONDecodeError:
    raise SystemExit(1)
today = datetime.now(timezone.utc).date().isoformat()
unscored = int(h.get('unscored_runners') or 0)
nan_ok = h.get('nan_integrity_passed')
sync = h.get('db_ui_in_sync')
card_fresh = h.get('card_fresh')
latest = h.get('latest_card_date')
tel = h.get('telemetry_balance') if isinstance(h.get('telemetry_balance'), dict) else {}
tel_ok = tel.get('passed')
runners = int(h.get('runners_loaded') or 0)
# Structural blockers
if unscored > 0:
    raise SystemExit(0)
if nan_ok is False:
    raise SystemExit(0)
if sync is False:
    raise SystemExit(0)
# Card freshness (after 08:00 UTC expect today's card on VPS)
hour = datetime.now(timezone.utc).hour
if hour >= 8 and runners > 0 and card_fresh is False:
    raise SystemExit(0)
if hour >= 8 and runners == 0 and latest and str(latest) < today:
    raise SystemExit(0)
if hour >= 10 and tel_ok is False:
    raise SystemExit(0)
raise SystemExit(1)
" <<<"${body}"
}

racing_value_lane_matchbook_poll() {
  local app="${1:-/opt/hibs-racing}"
  local bet="${2:-/opt/hibs-bet}"
  local cli="${app}/.venv/bin/hibs-racing"
  local env_file="${app}/.env"
  # shellcheck source=lib_matchbook_env.sh
  source "${bet}/scripts/lib_matchbook_env.sh"
  matchbook_load_env "${env_file}"
  if ! matchbook_credentials_ok; then
    echo "WARN: MATCHBOOK_USER/PASSWORD missing — skip poll" >&2
    return 0
  fi
  if [[ -x "${bet}/scripts/test_matchbook_credentials.sh" ]]; then
    bash "${bet}/scripts/test_matchbook_credentials.sh" "${env_file}" || return 1
  fi
  [[ -x "${cli}" ]] || return 0
  local try poll_cmds
  poll_cmds=""
  if [[ -f "${app}/scripts/daily_refresh.sh" ]]; then
    poll_cmds="$(grep -oE 'hibs-racing [^|;&]+' "${app}/scripts/daily_refresh.sh" 2>/dev/null \
      | grep -iE 'poll|matchbook|exchange|quote' | sort -u || true)"
  fi
  if [[ -n "${poll_cmds}" ]]; then
    while IFS= read -r cmd; do
      [[ -n "${cmd}" ]] || continue
      echo "==> ${cmd}"
      racing_value_lane_www_data_exec "${app}" "HIBS_POLL_MILESTONE=baseline ${cmd}" || true
    done <<<"${poll_cmds}"
    return 0
  fi
  for try in \
    "poll-matchbook" \
    "poll-exchange --source matchbook" \
    "fetch-odds --source matchbook" \
    "poll-quotes --source matchbook"; do
    echo "==> try: ${try}"
    if racing_value_lane_www_data_exec "${app}" "HIBS_POLL_MILESTONE=baseline '${cli}' ${try}"; then
      echo "OK: ${try}"
      return 0
    fi
  done
  echo "WARN: no Matchbook poll CLI succeeded — odds may rely on fetch-cards --score" >&2
  return 0
}

racing_value_lane_rescore() {
  local app="${1:-/opt/hibs-racing}"
  local bet="${2:-/opt/hibs-bet}"
  local cli="${app}/.venv/bin/hibs-racing"
  local year rf paid_ok=0
  # shellcheck source=lib_racing_vps_probe.sh
  source "${bet}/scripts/lib_racing_vps_probe.sh"
  [[ -x "${cli}" ]] || { echo "ERROR: ${cli} missing" >&2; return 1; }
  racing_value_lane_fix_env "${app}" "${bet}"
  racing_vps_repair_raceform_env "${app}" || return 1
  rf="$(racing_vps_resolve_raceform "${app}")"
  year="$(date +%Y)"

  racing_vps_kill_stale_gunicorn

  echo "==> ingest-raceform ${rf} --year ${year}"
  racing_value_lane_www_data_exec "${app}" \
    "RACEFORM_DB_PATH='${rf}' ${cli} ingest-raceform '${rf}' --year '${year}' --pipeline" || \
    echo "WARN: ingest-raceform failed — continuing" >&2

  local day
  for day in 0 1; do
    echo "==> fetch-cards --day ${day} --score"
    if racing_value_lane_www_data_exec "${app}" \
      "RACEFORM_DB_PATH='${rf}' HIBS_ODDS_SOURCE=auto ${cli} fetch-cards --source racing_api --day ${day} --score --odds-source auto"; then
      paid_ok=1
    else
      echo "WARN: fetch-cards --day ${day} failed — score-cards fallback" >&2
      racing_value_lane_www_data_exec "${app}" \
        "${cli} score-cards --day ${day}" 2>/dev/null || true
    fi
  done

  if [[ "${paid_ok}" -eq 0 && -f "${bet}/scripts/vps_racing_fetch_free_tier.sh" ]]; then
    echo "==> free-tier card fetch fallback"
    bash "${bet}/scripts/vps_racing_fetch_free_tier.sh" || true
    for day in 0 1; do
      racing_value_lane_www_data_exec "${app}" "${cli} score-cards --day ${day}" 2>/dev/null || true
    done
  fi

  racing_value_lane_matchbook_poll "${app}" "${bet}" || true
  racing_vps_fix_data_permissions "${app}" 2>/dev/null || true
}

racing_value_lane_restart_verify() {
  local app="${1:-/opt/hibs-racing}"
  local bet="${2:-/opt/hibs-bet}"
  # shellcheck source=lib_racing_vps_probe.sh
  source "${bet}/scripts/lib_racing_vps_probe.sh"
  racing_vps_fix_systemd_wsgi "${app}" "${bet}" 2>/dev/null || true
  racing_vps_restart_and_wait 90 60
}

racing_value_lane_run_full() {
  local app="${1:-/opt/hibs-racing}"
  local bet="${2:-/opt/hibs-bet}"
  if [[ -f "${app}/scripts/daily_refresh.sh" ]]; then
    echo "==> hibs-racing daily_refresh.sh (www-data + .env)"
    racing_value_lane_fix_env "${app}" "${bet}"
    # shellcheck source=lib_racing_vps_probe.sh
    source "${bet}/scripts/lib_racing_vps_probe.sh"
    racing_vps_kill_stale_gunicorn
    racing_value_lane_www_data_exec "${app}" "bash scripts/daily_refresh.sh" || {
      echo "WARN: daily_refresh failed — CLI rescore fallback" >&2
      racing_value_lane_rescore "${app}" "${bet}" || return 1
    }
  else
    racing_value_lane_rescore "${app}" "${bet}" || return 1
  fi
  racing_value_lane_restart_verify "${app}" "${bet}"
}

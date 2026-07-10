#!/usr/bin/env bash
# Shared racing VPS probes — port backlog, gunicorn kill, systemd WSGI, raceform paths.
# shellcheck shell=bash

racing_vps_canonical_raceform() {
  local app="${1:-/opt/hibs-racing}"
  echo "${app}/data/raceform.db"
}

racing_vps_resolve_raceform() {
  local app="${1:-/opt/hibs-racing}"
  local env_file="${app}/.env"
  local path=""
  if [[ -f "${env_file}" ]]; then
    path="$(grep -E '^RACEFORM_DB_PATH=' "${env_file}" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"' || true)"
  fi
  if [[ -n "${path}" && -f "${path}" ]]; then
    echo "${path}"
    return 0
  fi
  path="$(racing_vps_canonical_raceform "${app}")"
  echo "${path}"
}

racing_vps_repair_raceform_env() {
  local app="${1:-/opt/hibs-racing}"
  local env_file="${app}/.env"
  local canonical
  canonical="$(racing_vps_canonical_raceform "${app}")"
  [[ -f "${canonical}" ]] || return 1
  touch "${env_file}"
  if ! grep -qE '^RACEFORM_DB_PATH=' "${env_file}" 2>/dev/null; then
    echo "RACEFORM_DB_PATH=${canonical}" >>"${env_file}"
  else
    sed -i "s|^RACEFORM_DB_PATH=.*|RACEFORM_DB_PATH=${canonical}|" "${env_file}" 2>/dev/null || true
  fi
  chown www-data:www-data "${env_file}" 2>/dev/null || true
  return 0
}

racing_vps_port_backlog() {
  local port="${1:-5003}"
  ss -ltn "sport = :${port}" 2>/dev/null | awk 'NR>1 {print $2}' | head -1 || echo ""
}

racing_vps_accept_queue() {
  local port="${1:-5003}"
  local q
  q="$(ss -ltn "sport = :${port}" 2>/dev/null | awk 'NR>1 {print $2; exit}')"
  echo "${q:-0}"
}

racing_vps_kill_stale_gunicorn() {
  local port="${1:-5003}"
  systemctl stop hibs-racing 2>/dev/null || true
  sleep 1
  pkill -9 -f "gunicorn.*:${port}" 2>/dev/null || true
  pkill -9 -f "gunicorn.*hibs_racing" 2>/dev/null || true
  fuser -k "${port}/tcp" 2>/dev/null || true
  sleep 1
}

racing_vps_kill_football_gunicorn() {
  local port="${1:-8000}"
  systemctl stop hibs-bet 2>/dev/null || true
  sleep 1
  pkill -9 -f "gunicorn.*:${port}" 2>/dev/null || true
  pkill -9 -f "gunicorn.*hibs_predictor" 2>/dev/null || true
  fuser -k "${port}/tcp" 2>/dev/null || true
  sleep 1
}

racing_vps_fix_systemd_wsgi() {
  local app="${1:-/opt/hibs-racing}"
  local bet="${2:-/opt/hibs-bet}"
  local unit="/etc/systemd/system/hibs-racing.service"
  local src="${bet}/deploy/hibs-racing.service"
  local gcfg="${bet}/deploy/gunicorn-racing.conf.py"
  local app_gcfg="${app}/deploy/gunicorn-racing.conf.py"

  [[ -f "${src}" ]] && cp "${src}" "${unit}"
  [[ -f "${gcfg}" && ! -f "${app_gcfg}" ]] && mkdir -p "${app}/deploy" && cp "${gcfg}" "${app_gcfg}"

  if [[ -f "${unit}" ]]; then
    if ! grep -q 'HIBS_RACING_GUNICORN_APP=' "${unit}" 2>/dev/null; then
      sed -i '/^\[Service\]/a Environment=HIBS_RACING_GUNICORN_APP=hibs_racing.web:create_app()' "${unit}" 2>/dev/null || true
    fi
    if grep -q 'hibs_racing.web:app' "${unit}" 2>/dev/null; then
      sed -i 's/hibs_racing\.web:app/hibs_racing.web:create_app()/g' "${unit}" 2>/dev/null || true
    fi
  fi
  systemctl daemon-reload 2>/dev/null || true
}

racing_vps_fix_football_systemd() {
  local bet="${1:-/opt/hibs-bet}"
  local unit="/etc/systemd/system/hibs-bet.service"
  local src="${bet}/deploy/hibs-bet.service"
  [[ -f "${src}" ]] && cp "${src}" "${unit}"
  systemctl daemon-reload 2>/dev/null || true
}

racing_vps_fix_data_permissions() {
  local app="${1:-/opt/hibs-racing}"
  chown -R www-data:www-data "${app}/data" "${app}/.env" 2>/dev/null || true
  chmod 640 "${app}/.env" 2>/dev/null || true
}

racing_vps_wait_port() {
  local port="$1"
  local timeout="${2:-90}"
  local i=0
  while [[ "${i}" -lt "${timeout}" ]]; do
    if ss -ltn "sport = :${port}" 2>/dev/null | grep -q ":${port}"; then
      echo "${i}"
      return 0
    fi
    sleep 1
    i=$((i + 1))
  done
  return 1
}

racing_vps_wait_http() {
  local url="$1"
  local timeout="${2:-60}"
  local i=0
  while [[ "${i}" -lt "${timeout}" ]]; do
    local code
    code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "${url}" 2>/dev/null || echo 000)"
    if [[ "${code}" == "200" ]]; then
      echo "${i}"
      return 0
    fi
    sleep 1
    i=$((i + 1))
  done
  return 1
}

racing_vps_restart_and_wait() {
  local port_timeout="${1:-90}"
  local ping_timeout="${2:-60}"
  systemctl reset-failed hibs-racing 2>/dev/null || true
  systemctl start hibs-racing 2>/dev/null || systemctl restart hibs-racing 2>/dev/null || true
  racing_vps_wait_port 5003 "${port_timeout}" || return 1
  racing_vps_wait_http "http://127.0.0.1:5003/api/ping" "${ping_timeout}" || return 1
}

racing_vps_football_restart_and_wait() {
  local port_timeout="${1:-90}"
  local ping_timeout="${2:-60}"
  systemctl reset-failed hibs-bet 2>/dev/null || true
  systemctl start hibs-bet 2>/dev/null || systemctl restart hibs-bet 2>/dev/null || true
  racing_vps_wait_port 8000 "${port_timeout}" || return 1
  racing_vps_wait_http "http://127.0.0.1:8000/api/ping" "${ping_timeout}" || return 1
}

racing_vps_sqlite_has_cards() {
  local app="${1:-/opt/hibs-racing}"
  local db="${app}/data/feature_store.sqlite"
  [[ -f "${db}" ]] || return 1
  local py="${app}/.venv/bin/python3"
  [[ -x "${py}" ]] || py=python3
  HOME="${app}" "${py}" -c "
import sqlite3, sys
con = sqlite3.connect('${db}')
n = con.execute('SELECT COUNT(*) FROM runners WHERE 1=1').fetchone()[0]
sys.exit(0 if int(n or 0) > 0 else 1)
" 2>/dev/null
}

racing_vps_ensure_football_secret() {
  local bet="${1:-/opt/hibs-bet}"
  local env_file="${bet}/.env"
  touch "${env_file}"
  if grep -qE '^HIBS_AUTH_ENABLED=1' "${env_file}" 2>/dev/null; then
    if ! grep -qE '^HIBS_SECRET_KEY=.+' "${env_file}" 2>/dev/null; then
      local sk
      sk="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
      echo "HIBS_SECRET_KEY=${sk}" >>"${env_file}"
      echo "auto-generated HIBS_SECRET_KEY (auth enabled)"
    fi
  fi
  chown www-data:www-data "${env_file}" 2>/dev/null || true
}

racing_vps_patch_football_auth_dashboard() {
  local bet="${1:-/opt/hibs-bet}"
  local auth="${bet}/src/hibs_predictor/auth.py"
  [[ -f "${auth}" ]] || return 0
  if grep -q 'url_for("dashboard")' "${auth}" 2>/dev/null; then
    sed -i 's/url_for("dashboard")/url_for("index")/g' "${auth}"
    echo "patched auth.py: dashboard -> index"
  fi
}

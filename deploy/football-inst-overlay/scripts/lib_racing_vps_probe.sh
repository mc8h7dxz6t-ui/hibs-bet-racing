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

football_vps_diagnose_502() {
  local bet="${1:-/opt/hibs-bet}"
  local unit port local_login nginx_login
  unit="$(systemctl is-active hibs-bet 2>/dev/null || echo inactive)"
  if ss -ltn 2>/dev/null | grep -q ':8000 '; then
    port=up
  else
    port=down
  fi
  local_login="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 6 http://127.0.0.1:8000/login 2>/dev/null || echo 000)"
  nginx_login="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 -k https://127.0.0.1/login -H 'Host: hibs-bet.co.uk' 2>/dev/null || echo 000)"
  echo "hibs-bet unit: ${unit}"
  echo ":8000 listen: ${port}"
  echo "localhost /login: ${local_login}"
  echo "nginx /login (loopback): ${nginx_login}"
  if [[ -d /etc/nginx/sites-enabled ]]; then
    echo "nginx football upstreams:"
    grep -RhnE 'proxy_pass|upstream hibs_football|127\.0\.0\.1:(5001|8000)' /etc/nginx/sites-enabled/ 2>/dev/null | head -20 || true
  fi
  if [[ "${unit}" == "active" && "${port}" == "down" ]]; then
    echo "DIAGNOSIS: systemd active but :8000 down — gunicorn crashed (journalctl -u hibs-bet)"
  elif [[ "${port}" == "up" && "${local_login}" =~ ^(200|302)$ && "${nginx_login}" == "502" ]]; then
    echo "DIAGNOSIS: app OK locally, nginx 502 — wrong upstream (often :5001 not :8000)"
  elif [[ "${port}" == "down" && "${local_login}" == "000" ]]; then
    echo "DIAGNOSIS: gunicorn not running — import test alone does not start the service"
  fi
}

football_vps_fix_nginx_upstream() {
  local bet="${1:-/opt/hibs-bet}"
  local fixed=0
  local f site_avail="/etc/nginx/sites-available/hibs-bet"
  local site_enabled="/etc/nginx/sites-enabled/hibs-bet"

  if [[ -f "${bet}/deploy/hibs-bet.nginx.conf" ]]; then
    if [[ ! -f "${site_avail}" ]] || ! grep -qE 'proxy_pass http://127\.0\.0\.1:8000' "${site_avail}" 2>/dev/null; then
      cp "${bet}/deploy/hibs-bet.nginx.conf" "${site_avail}"
      ln -sf "${site_avail}" "${site_enabled}"
      echo "installed canonical hibs-bet.nginx.conf → ${site_avail}"
      fixed=1
    fi
  fi

  if [[ -L /etc/nginx/sites-enabled/hibs-unified ]] || [[ -f /etc/nginx/sites-enabled/hibs-unified ]]; then
    if grep -qE '127\.0\.0\.1:5001|upstream hibs_football' /etc/nginx/sites-enabled/hibs-unified 2>/dev/null; then
      rm -f /etc/nginx/sites-enabled/hibs-unified
      echo "disabled hibs-unified (dev :5001 conflicts with gunicorn :8000)"
      fixed=1
    fi
  fi

  for f in /etc/nginx/sites-available/* /etc/nginx/sites-enabled/*; do
    [[ -f "${f}" ]] || continue
    if grep -qE '127\.0\.0\.1:5001|server 127\.0\.0\.1:5001' "${f}" 2>/dev/null; then
      sed -i 's|127\.0\.0\.1:5001|127.0.0.1:8000|g' "${f}"
      sed -i 's|server 127\.0\.0\.1:5001|server 127.0.0.1:8000|g' "${f}"
      echo "patched nginx upstream 5001→8000: ${f}"
      fixed=1
    fi
    if grep -qE 'proxy_pass http://hibs_football' "${f}" 2>/dev/null && \
       grep -qE 'upstream hibs_football' "${f}" 2>/dev/null; then
      sed -i '/upstream hibs_football/,/}/ s|server 127\.0\.0\.1:5001|server 127.0.0.1:8000|g' "${f}"
      echo "patched upstream hibs_football block: ${f}"
      fixed=1
    fi
  done

  if [[ "${fixed}" -eq 1 ]] && command -v nginx >/dev/null 2>&1; then
    nginx -t && systemctl reload nginx
    echo "nginx reloaded"
  fi
  return 0
}

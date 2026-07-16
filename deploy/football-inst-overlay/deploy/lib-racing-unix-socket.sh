#!/usr/bin/env bash
# Helpers for probing hibs-racing via UNIX domain socket (replaces :5003 TCP loopback).
set -euo pipefail

HIBS_RACING_UNIX_SOCKET="${HIBS_RACING_UNIX_SOCKET:-/var/run/hibs/racing_execution.sock}"
HIBS_RACING_PING_URL="${HIBS_RACING_PING_URL:-http://localhost/api/ping}"

racing_curl() {
  local path="${1:-/api/ping}"
  curl -sS --unix-socket "${HIBS_RACING_UNIX_SOCKET}" --max-time "${2:-12}" "http://localhost${path}"
}

racing_ping_code() {
  curl -sS -o /dev/null -w '%{http_code}' --unix-socket "${HIBS_RACING_UNIX_SOCKET}" \
    --max-time "${1:-12}" "http://localhost/api/ping" 2>/dev/null || echo 000
}

racing_wait_ping() {
  local timeout="${1:-60}"
  local start
  start="$(date +%s)"
  while true; do
    if [[ "$(racing_ping_code 8)" == "200" ]]; then
      return 0
    fi
    if (( $(date +%s) - start >= timeout )); then
      return 1
    fi
    sleep 2
  done
}

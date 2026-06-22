#!/usr/bin/env bash
# Probe trading metrics daemon (/live always 200 when up; /ready may be 503 while warming).
# Usage: source scripts/lib_trading_probe.sh && trading_probe_status 9108
set -euo pipefail

trading_probe_status() {
  local port="${1:?port}"
  local live_body ready_body ready_code
  live_body="$(curl -s --max-time 5 "http://127.0.0.1:${port}/live" 2>/dev/null || true)"
  if [[ "${live_body}" != *NODE_ALIVE* ]]; then
    echo "down"
    return 0
  fi
  ready_body="$(curl -s --max-time 5 -w $'\n%{http_code}' "http://127.0.0.1:${port}/ready" 2>/dev/null || echo -e "\n000")"
  ready_code="${ready_body##*$'\n'}"
  ready_body="${ready_body%$'\n'*}"
  if [[ "${ready_code}" == "200" && "${ready_body}" == *NODE_READY* ]]; then
    echo "ready"
    return 0
  fi
  if [[ "${ready_code}" == "503" ]]; then
    local reason="${ready_body#NODE_UNREADY: }"
    reason="${reason%%$'\n'*}"
    echo "warming:${reason:-boot}"
    return 0
  fi
  echo "live"
}

trading_probe_wait_ready() {
  local port="${1:?port}"
  local max_sec="${2:-45}"
  local t=0 st
  while [[ "${t}" -lt "${max_sec}" ]]; do
    st="$(trading_probe_status "${port}")"
    if [[ "${st}" == "ready" ]]; then
      echo "ready"
      return 0
    fi
    if [[ "${st}" == "down" ]]; then
      sleep 2
      t=$((t + 2))
      continue
    fi
    sleep 3
    t=$((t + 3))
  done
  trading_probe_status "${port}"
}

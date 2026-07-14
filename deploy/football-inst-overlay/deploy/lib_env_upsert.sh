#!/usr/bin/env bash
# Idempotent .env upsert + dedupe (institutional — no duplicate KEY= lines).
# shellcheck shell=bash
set -euo pipefail

env_upsert() {
  local file="$1" key="$2" val="$3"
  touch "${file}"
  if grep -q "^${key}=" "${file}" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" "${file}"
  else
    echo "${key}=${val}" >>"${file}"
  fi
}

env_dedupe_file() {
  local file="$1"
  [[ -f "${file}" ]] || return 0
  local tmp
  tmp="$(mktemp)"
  awk '
    /^[[:space:]]*#/ { print; next }
    /^[[:space:]]*$/ { print; next }
    /^[A-Za-z_][A-Za-z0-9_]*=/ { split($0, a, "="); k = a[1]; kv[k] = $0; next }
    { print }
    END { for (k in kv) print kv[k] }
  ' "${file}" >"${tmp}"
  mv "${tmp}" "${file}"
}

env_ensure_keys() {
  local file="$1"
  shift
  while [[ $# -ge 2 ]]; do
    env_upsert "${file}" "$1" "$2"
    shift 2
  done
}

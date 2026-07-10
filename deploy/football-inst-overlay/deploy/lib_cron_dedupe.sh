#!/usr/bin/env bash
# Managed cron markers — dedupe www-data crontab lines for hibs-bet automation.
# shellcheck shell=bash

HIBS_CRON_MARKERS=(
  "hibs-bet: daily bundle"
  "hibs-bet: seed forward evidence"
  "hibs-bet: hands-off cycle"
  "hibs-bet: institutional++ watchdog"
  "hibs-bet: nine-ten daily"
  "hibs-bet: calibration drift"
  "hibs-bet: football fixture warm"
  "hibs-bet: ops automation"
  "hibs: cross-platform prediction results"
  "hibs-racing"
)

hibs_crontab_purge_managed() {
  local existing filtered line keep
  existing="$(crontab -u www-data -l 2>/dev/null || true)"
  filtered=""
  while IFS= read -r line || [[ -n "${line}" ]]; do
    keep=1
    for marker in "${HIBS_CRON_MARKERS[@]}"; do
      if [[ "${line}" == *"${marker}"* ]]; then
        keep=0
        break
      fi
    done
    if [[ "${keep}" -eq 1 ]]; then
      filtered+="${line}"$'\n'
    fi
  done <<<"${existing}"
  printf '%s' "${filtered}" | crontab -u www-data -
}

hibs_crontab_verify_managed() {
  local text dup=0
  text="$(crontab -u www-data -l 2>/dev/null || true)"
  for marker in "${HIBS_CRON_MARKERS[@]}"; do
    local count
    count="$(printf '%s\n' "${text}" | grep -cF "${marker}" || true)"
    if [[ "${count}" -gt 1 ]]; then
      echo "DUPLICATE marker (${count}x): ${marker}" >&2
      dup=1
    fi
  done
  return "${dup}"
}

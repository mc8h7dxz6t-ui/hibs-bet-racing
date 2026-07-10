#!/usr/bin/env bash
# Managed cron helpers — dedupe, stats, safe install guard.
# shellcheck shell=bash

HIBS_CRON_MARKERS=(
  "hibs-bet: daily bundle"
  "hibs-bet: seed forward evidence"
  "hibs-bet: hands-off cycle"
  "hibs-bet: infra fallback (5m)"
  "hibs-bet: institutional++ watchdog"
  "hibs-bet: nine-ten daily"
  "hibs-bet: calibration drift"
  "hibs-bet: football fixture warm"
  "hibs-bet: ops automation"
  "hibs: cross-platform prediction results"
  "hibs-racing"
  "hibs sports-only"
)

HIBS_CRON_MAX_LINES="${HIBS_CRON_MAX_LINES:-200}"

hibs_crontab_line_count() {
  local user="${1:-www-data}"
  crontab -u "${user}" -l 2>/dev/null | wc -l | tr -d ' '
}

hibs_crontab_stats() {
  local user="${1:-www-data}"
  local n hibs_n
  n="$(hibs_crontab_line_count "${user}")"
  hibs_n="$(crontab -u "${user}" -l 2>/dev/null | grep -c '/opt/hibs-bet' || true)"
  echo "user=${user} total_lines=${n} hibs_bet_lines=${hibs_n}"
}

hibs_crontab_dedupe_identical() {
  local user="${1:-www-data}"
  local existing tmp
  existing="$(crontab -u "${user}" -l 2>/dev/null || true)"
  tmp="$(mktemp)"
  printf '%s\n' "${existing}" | awk '
    /^[[:space:]]*#/ { print; next }
    /^[[:space:]]*$/ { next }
    { if (!seen[$0]++) print }
  ' >"${tmp}"
  crontab -u "${user}" "${tmp}"
  rm -f "${tmp}"
}

hibs_crontab_purge_hibs_paths() {
  local user="${1:-www-data}"
  local existing filtered
  existing="$(crontab -u "${user}" -l 2>/dev/null || true)"
  filtered="$(printf '%s\n' "${existing}" | \
    grep -v '/opt/hibs-bet' | \
    grep -v '/opt/hibs-racing' | \
    grep -v 'hibs-bet:' | \
    grep -v 'hibs-racing' | \
    grep -v 'run_daily_audit_pipeline' | \
    grep -v 'prediction_evidence_status' | \
    grep -v 'trade_scorecard' | \
    grep -v 'bankroll_sync' | \
    grep -v 'evidence_gate_refresh' | \
    grep -v 'train-from-audit' || true)"
  printf '%s\n' "${filtered}" | sed '/^$/d' | crontab -u "${user}" -
}

hibs_crontab_purge_managed() {
  hibs_crontab_purge_hibs_paths www-data
  hibs_crontab_dedupe_identical www-data
}

hibs_crontab_install_guard() {
  local user="${1:-www-data}"
  local n
  n="$(hibs_crontab_line_count "${user}")"
  if [[ "${n}" -gt "${HIBS_CRON_MAX_LINES}" ]]; then
    echo "ERROR: ${user} crontab has ${n} lines (max ${HIBS_CRON_MAX_LINES})." >&2
    echo "Run: sudo bash /opt/hibs-bet/deploy/crontab-emergency-sports-only.sh" >&2
    return 1
  fi
  return 0
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
  hibs_crontab_install_guard www-data || dup=1
  return "${dup}"
}

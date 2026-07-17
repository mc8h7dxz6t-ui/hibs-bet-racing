#!/usr/bin/env bash
# VPS one-shot: sync gate backtest scripts from GitHub, then run alignment matrix + sniper sweep.
#
#   sudo bash /opt/hibs-racing/scripts/vps_gate_backtests.sh
#   sudo bash /opt/hibs-racing/scripts/vps_gate_backtests.sh 2025-11-01 2026-06-30
#
# /opt/hibs-racing is rsync deploy — never use git pull there.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
START="${1:-2025-11-01}"
END="${2:-$(date -u +%Y-%m-%d)}"
REF="${HIBS_RACING_SYNC_REF:-cursor/gate-config-alignment-12e0}"

_gate_scripts_present() {
  [[ -f "${ROOT}/scripts/gate_alignment_matrix.sh" ]] \
    && [[ -f "${ROOT}/src/hibs_racing/backtest/gate_config_alignment.py" ]] \
    && [[ -f "${ROOT}/src/hibs_racing/backtest/sniper_overlay_sweep.py" ]]
}

_find_sync_script() {
  local c
  for c in \
    "${ROOT}/deploy/vps-sync-racing-from-github.sh" \
    "/opt/hibs-bet/deploy/vps-sync-racing-from-github.sh" \
    "${ROOT}/deploy/football-inst-overlay/deploy/vps-sync-racing-from-github.sh"; do
    if [[ -f "$c" ]]; then
      echo "$c"
      return 0
    fi
  done
  return 1
}

if ! _gate_scripts_present; then
  echo "==> Gate backtest scripts missing on VPS — syncing from GitHub ref=${REF}"
  echo "    (Do NOT use git pull — /opt/hibs-racing is not a git repository)"
  SYNC="$(_find_sync_script || true)"
  if [[ -z "${SYNC}" ]]; then
    echo "ERROR: no vps-sync-racing-from-github.sh found." >&2
    echo "  Copy deploy/vps-sync-racing-from-github.sh from hibs-bet-racing repo first." >&2
    exit 1
  fi
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "Run as root: sudo HIBS_RACING_SYNC_REF=${REF} bash ${SYNC}" >&2
    exit 1
  fi
  HIBS_RACING_SYNC_REF="${REF}" bash "${SYNC}"
fi

export HIBS_HARVILLE_CORRECTION="${HIBS_HARVILLE_CORRECTION:-1}"
export HIBS_RACING_DB_PATH="${HIBS_RACING_DB_PATH:-/mnt/hibs-ramdisk/feature_store.sqlite}"

echo ""
echo "==> 1/2 Gate alignment matrix"
bash "${ROOT}/scripts/gate_alignment_matrix.sh" "${START}" "${END}"

echo ""
echo "==> 2/2 Sniper overlay sweep"
bash "${ROOT}/scripts/sniper_overlay_sweep.sh" "${START}" "${END}"

echo ""
echo "==> Outputs:"
echo "    ${ROOT}/exports/gate_alignment_matrix.md"
echo "    ${ROOT}/exports/sniper_overlay_sweep.json"
if [[ -f "${ROOT}/exports/gate_alignment_matrix.md" ]]; then
  echo ""
  cat "${ROOT}/exports/gate_alignment_matrix.md"
fi

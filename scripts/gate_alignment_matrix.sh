#!/usr/bin/env bash
# Forensic gate alignment: 3 industry standards → 3 aligned overlays → 2 blends → full table.
# VPS: sync first — /opt/hibs-racing is NOT a git repo.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck source=lib_backtest_db.sh
source "${ROOT}/scripts/lib_backtest_db.sh"
pick_backtest_db || true

if [[ ! -f "${ROOT}/scripts/gate_alignment_matrix.py" ]]; then
  echo "ERROR: gate_alignment_matrix.py missing — sync racing from GitHub first:" >&2
  echo "  sudo HIBS_RACING_SYNC_REF=cursor/gate-config-alignment-12e0 \\" >&2
  echo "    bash /opt/hibs-bet/deploy/vps-sync-racing-from-github.sh" >&2
  echo "  Or: sudo bash ${ROOT}/scripts/vps_gate_backtests.sh" >&2
  exit 1
fi

export HIBS_HARVILLE_CORRECTION="${HIBS_HARVILLE_CORRECTION:-1}"
export HIBS_RACING_DB_PATH="${HIBS_RACING_DB_PATH:-/mnt/hibs-ramdisk/feature_store.sqlite}"

START="${1:-2025-11-01}"
END="${2:-$(date -u +%Y-%m-%d)}"

PY="${ROOT}/.venv/bin/python3"
if [[ ! -x "$PY" ]]; then
  PY="python3"
  export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
fi

echo "==> Gate alignment matrix ${START} → ${END}"
"$PY" scripts/gate_alignment_matrix.py --start "$START" --end "$END"

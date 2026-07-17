#!/usr/bin/env bash
# Forensic gate alignment: 3 industry standards → 3 aligned overlays → 2 blends → full table.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

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

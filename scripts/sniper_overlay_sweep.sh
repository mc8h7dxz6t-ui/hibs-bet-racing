#!/usr/bin/env bash
# Walk-forward sweep of 8 sniper gate overlays — run on VPS with snapshot backfill.
# VPS: sync first — /opt/hibs-racing is NOT a git repo. Use:
#   sudo HIBS_RACING_SYNC_REF=cursor/gate-config-alignment-12e0 \
#     bash /opt/hibs-bet/deploy/vps-sync-racing-from-github.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f "${ROOT}/src/hibs_racing/backtest/sniper_overlay_sweep.py" ]]; then
  echo "ERROR: sniper_overlay_sweep.py missing — sync racing from GitHub first:" >&2
  echo "  sudo HIBS_RACING_SYNC_REF=cursor/gate-config-alignment-12e0 \\" >&2
  echo "    bash /opt/hibs-bet/deploy/vps-sync-racing-from-github.sh" >&2
  echo "  Or: sudo bash ${ROOT}/scripts/vps_gate_backtests.sh" >&2
  exit 1
fi

export HIBS_HARVILLE_CORRECTION="${HIBS_HARVILLE_CORRECTION:-1}"
export HIBS_RACING_DB_PATH="${HIBS_RACING_DB_PATH:-/mnt/hibs-ramdisk/feature_store.sqlite}"

START="${1:-2025-11-01}"
END="${2:-$(date -u +%Y-%m-%d)}"
OUT="${ROOT}/exports/sniper_overlay_sweep.json"

PY="${ROOT}/.venv/bin/hibs-racing"
if [[ ! -x "$PY" ]]; then
  PY="python3 -m hibs_racing.cli"
  export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
fi

echo "==> Sniper overlay sweep ${START} → ${END}"
echo "    DB: ${HIBS_RACING_DB_PATH}"

$PY sniper-overlay-sweep \
  --start "$START" \
  --end "$END" \
  --output "$OUT"

echo "==> Done. Ranking:"
python3 - <<'PY'
import json
import sys
from pathlib import Path

p = Path("exports/sniper_overlay_sweep.json")
if not p.exists():
    sys.exit(0)
data = json.loads(p.read_text())
for i, row in enumerate(data.get("ranking", []), 1):
    roi = row.get("aggregate_roi_pct")
    picks = row.get("total_picks")
    ready = row.get("promotion_ready")
    print(f"  {i}. {row['overlay_id']}: roi={roi}% picks={picks} promotion_ready={ready}")
best = data.get("best_overlay")
if best:
    print(f"==> Best overlay: {best}")
PY

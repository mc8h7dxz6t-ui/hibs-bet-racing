#!/usr/bin/env bash
# One-shot buyer evidence pack — plug, demo all 12 SKUs, offline verify every bundle.
#
# Usage:
#   ./scripts/instpp_buyer_pack.sh           # full pack (offline-safe)
#   SKIP_SMOKE=1 ./scripts/instpp_buyer_pack.sh   # skip pytest pre-check
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
# shellcheck source=instpp_bootstrap.sh
source "$(dirname "$0")/instpp_bootstrap.sh"
instpp_bootstrap

export SKIP_LIVE="${SKIP_LIVE:-1}"
export SKIP_LIVE_LLM="${SKIP_LIVE_LLM:-1}"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  INSTITUTIONAL++ BUYER PACK — plug / demo / verify           ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

pip install -e ".[dev,instpp]" -q

if [[ "${SKIP_SMOKE:-0}" != "1" ]]; then
  echo "── Pre-check: institutional smoke ──"
  ./scripts/instpp_smoke_test.sh
fi

echo ""
echo "── Portfolio demo: 12/12 SKUs ──"
./scripts/demo_portfolio_all.sh --clean

echo ""
echo "── Offline verify-bundle: 12/12 tarballs ──"
./scripts/verify_portfolio.sh

ENDED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
PACK_DIR="${PORTFOLIO_DEMO_DIR:-./data/demo/portfolio}"

"$PYTHON" - <<PY
import json
from pathlib import Path

pack = Path("${PACK_DIR}")
manifest = json.loads((pack / "PORTFOLIO_MANIFEST.json").read_text())
summary = {
    "suite": "instpp_buyer_pack",
    "status": manifest.get("status", "UNKNOWN"),
    "products": manifest.get("products", 12),
    "verified_ok": manifest.get("verified_ok", 0),
    "started_utc": "${STARTED_AT}",
    "finished_utc": "${ENDED_AT}",
    "demo_dir": str(pack),
    "manifest": str(pack / "PORTFOLIO_MANIFEST.json"),
    "next_steps": [
        "make demo-gold          # spend-plane sales walkthrough",
        "make demo-gold-up       # Proof Console UI",
        "make rigorous           # full rigorous E2E log",
    ],
}
out = pack / "BUYER_PACK_SUMMARY.json"
out.write_text(json.dumps(summary, indent=2) + "\\n")
print(json.dumps(summary, indent=2))
PY

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  BUYER PACK COMPLETE — evidence in data/demo/portfolio/      ║"
echo "╚══════════════════════════════════════════════════════════════╝"

#!/usr/bin/env bash
# AI Kit demo — run → check → export → verify-bundle.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
TRACE="${1:-./data/demo/ai_kit_trace.sqlite}"
TAR="${2:-./data/demo/ai_kit_bundle.tar}"
mkdir -p "$(dirname "$TRACE")" "$(dirname "$TAR")"
echo "── 1/4 Agent run (checkpoint + trace) ──"
"$PYTHON" -m ai_kit.cli run --steps 3 --trace-db "$TRACE" --max-tokens 1000
echo "── 2/4 F1–F9 check ──"
"$PYTHON" -m ai_kit.cli check --database "$TRACE"
echo "── 3/4 Export bundle ──"
"$PYTHON" -m ai_kit.cli export --database "$TRACE" --tarball "$TAR"
echo "── 4/4 Verify offline ──"
"$PYTHON" -m ai_kit.cli verify-bundle --tarball "$TAR"
echo "[PASS] AI Kit demo → $TAR"

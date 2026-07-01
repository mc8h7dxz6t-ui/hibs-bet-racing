#!/usr/bin/env bash
# F8 retention drill — epoch compaction + export verify (Wave 2).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"

echo "==> F8 retention drill"
"$PYTHON" -m pytest tests/test_retention_drill.py -v --tb=short
echo "[PASS] F8 retention drill"

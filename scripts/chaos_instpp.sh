#!/usr/bin/env bash
# Industry gold chaos + integration drills — WAL, capture, wallet, drift persistence.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
# shellcheck source=instpp_bootstrap.sh
source "$(dirname "$0")/instpp_bootstrap.sh"
instpp_bootstrap

echo "==> Industry gold chaos suite"
pip install -e ".[dev,instpp]" -q
"$PYTHON" -m pytest tests/test_industry_gold.py -v --tb=short
echo "[PASS] Industry gold chaos suite"

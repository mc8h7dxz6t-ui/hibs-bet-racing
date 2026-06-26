#!/usr/bin/env bash
# Offline verify-bundle for all 12 portfolio tarballs after make demo-all.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
# shellcheck source=instpp_bootstrap.sh
source "$(dirname "$0")/instpp_bootstrap.sh"
instpp_bootstrap

pip install -e ".[dev,instpp]" -q
exec "$PYTHON" "$(dirname "$0")/verify_portfolio.py"

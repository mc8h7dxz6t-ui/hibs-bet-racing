#!/usr/bin/env bash
# PR proof-lite — production profile gates + portfolio offline verify (no rigorous E2E).
set -euo pipefail

cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python3}"
# shellcheck source=instpp_bootstrap.sh
source "$(dirname "$0")/instpp_bootstrap.sh"
instpp_bootstrap

echo "==> Installing institutional dev dependencies"
pip install -e ".[dev,instpp]" -q

echo "==> Production profile + SKU hardening tests"
"$PYTHON" -m pytest \
  tests/test_production_profile.py \
  tests/test_sku_layer_hardening.py \
  tests/test_production_profile_serve_ready.py \
  tests/test_phase3_buyer_depth.py \
  -q

echo "==> Seed 12/12 portfolio (offline)"
SKIP_LIVE=1 ./scripts/demo_portfolio_all.sh

echo "==> Offline verify-bundle 12/12"
./scripts/verify_portfolio.sh

"$PYTHON" ./scripts/instpp_ci_autonomy_log.py --suite proof-lite --status PASSED

echo ""
echo "INSTITUTIONAL PROOF-LITE PASSED"
echo "Phase log: docs/test_logs/instpp_ci_autonomy_phases.json"
echo "Summary:   docs/test_logs/instpp_proof_lite_latest_summary.json"

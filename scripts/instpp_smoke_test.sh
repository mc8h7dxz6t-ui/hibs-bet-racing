#!/usr/bin/env bash
# Institutional smoke test — run before demo, advertise, or release.
set -euo pipefail

cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python3}"

echo "==> Installing institutional dev dependencies"
pip install -e ".[dev,instpp]" -q

echo "==> Running institutional test suite (all 7 products)"
"$PYTHON" -m pytest \
  tests/test_inst_spine_core.py \
  tests/test_inst_products.py \
  tests/test_inst_export.py \
  tests/test_proxy_risk.py \
  tests/test_inst_coverage.py \
  tests/test_compliance_cli.py \
  tests/test_altdata_cli.py \
  tests/test_ai_kit_cli.py \
  tests/test_ad_guard_cli.py \
  tests/test_webhook_mesh.py \
  tests/test_ad_guard.py \
  tests/test_health_telemetry.py \
  -q

echo "==> Compliance export repro-check (ephemeral DB)"
TMP_DB="$(mktemp --suffix=.sqlite)"
export TMP_DB
"$PYTHON" - <<'PY'
import json
import tempfile
from pathlib import Path
from compliance_log.ingest import log_decision
from inst_spine.export import verify_bundle_reproducible

db = Path(tempfile.mkstemp(suffix=".sqlite")[1])
log_decision(
    snapshot={"decision": "approve", "amount": 100},
    outcome={"status": "ok"},
    actor="smoke-test",
    database=db,
)
ok, msg = verify_bundle_reproducible(db)
print(json.dumps({"repro_check": ok, "message": msg}))
raise SystemExit(0 if ok else 1)
PY

echo ""
echo "INSTITUTIONAL SMOKE TEST PASSED (7/7 products)"
echo "Ready to demo:"
echo "  ./scripts/demo_instpp.sh              # compliance + proxy (~60s)"
echo "  ./scripts/demo_altdata.sh             # product #3"
echo "  ./scripts/demo_ai_kit.sh              # product #4"
echo "  ./scripts/demo_webhook_mesh.sh        # product #5"
echo "  ./scripts/demo_ad_guard.sh            # product #6"
echo "  ./scripts/demo_health_telemetry.sh    # product #7"
echo "  ./scripts/instpp_rigorous_test.sh     # full E2E + log"
echo "See docs/INSTITUTIONAL_STANDARD.md"

#!/usr/bin/env bash
# Inst++ smoke test — run before demo, advertise, or release.
set -euo pipefail

cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python3}"

echo "==> Installing Inst++ dev dependencies"
pip install -e ".[dev,instpp]" -q

echo "==> Running Inst++ test suite"
"$PYTHON" -m pytest \
  tests/test_inst_spine_core.py \
  tests/test_inst_products.py \
  tests/test_inst_export.py \
  tests/test_proxy_risk.py \
  tests/test_webhook_mesh.py \
  tests/test_ad_guard.py \
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
echo "INST++ SMOKE TEST PASSED"
echo "Ready to demo:"
echo "  webhook-mesh serve --port 8787"
echo "  ad-guard serve --port 8788"
echo "  compliance-log ingest --snapshot docs/demo_snapshot.json  # optional"
echo "See docs/INST_PLUS_TEST_AND_DEMO.md"

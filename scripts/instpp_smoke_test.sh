#!/usr/bin/env bash
# Institutional smoke test — run before demo, advertise, or release.
set -euo pipefail

cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python3}"
# shellcheck source=instpp_bootstrap.sh
source "$(dirname "$0")/instpp_bootstrap.sh"
instpp_bootstrap

echo "==> Installing institutional dev dependencies"
pip install -e ".[dev,instpp]" -q

echo "==> Running institutional test suite (12 SKUs)"
"$PYTHON" -m pytest \
  tests/test_inst_spine_core.py \
  tests/test_inst_products.py \
  tests/test_inst_export.py \
  tests/test_proxy_risk.py \
  tests/test_compliance_serve.py \
  tests/test_proxy_risk_serve.py \
  tests/test_health_probes.py \
  tests/test_inst_coverage.py \
  tests/test_compliance_cli.py \
  tests/test_altdata_cli.py \
  tests/test_ai_kit_cli.py \
  tests/test_altdata_production.py \
  tests/test_ai_kit_llm.py \
  tests/test_ad_guard_creative.py \
  tests/test_webhook_mesh.py \
  tests/test_ad_guard.py \
  tests/test_health_telemetry.py \
  tests/test_model_governor.py \
  tests/test_drift_gate.py \
  tests/test_webhook_replay.py \
  tests/test_spend_guard.py \
  tests/test_agent_ledger.py \
  tests/test_forensic_tiers.py \
  tests/test_industry_gold.py \
  tests/test_inst_workflow.py \
  tests/test_drift_golden.py \
  tests/test_middleware_auth.py \
  tests/test_permit_ttl.py \
  tests/test_retention_drill.py \
  tests/test_altdata_structural_golden.py \
  tests/test_webhook_mesh_chaos.py \
  tests/test_bundle_sign.py \
  tests/test_production_profile.py \
  tests/test_sku_layer_hardening.py \
  tests/test_phase3_buyer_depth.py \
  -q

echo "==> Compliance export repro-check (ephemeral DB)"
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
echo "INSTITUTIONAL SMOKE TEST PASSED (12/12 Industry Gold)"
echo "Ready to demo:"
echo "  ./scripts/demo_instpp.sh              # compliance + proxy (~60s)"
echo "  ./scripts/demo_altdata.sh             # product #3"
echo "  ./scripts/demo_ai_kit.sh              # product #4"
echo "  ./scripts/demo_webhook_mesh.sh        # product #5"
echo "  ./scripts/demo_ad_guard.sh            # product #6"
echo "  ./scripts/demo_health_telemetry.sh    # product #7"
echo "  ./scripts/demo_model_governor.sh      # product #8"
echo "  ./scripts/demo_phase2_all.sh          # drift-gate + webhook-replay + spend-guard"
echo "  ./scripts/instpp_rigorous_test.sh     # full E2E + log"
echo "See docs/INSTITUTIONAL_STANDARD.md"

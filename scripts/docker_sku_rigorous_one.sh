#!/usr/bin/env bash
# Run ONE SKU extreme rigorous proof (intended inside Docker).
# Usage: ./scripts/docker_sku_rigorous_one.sh <sku-id>
#   sku-id: compliance | proxy | altdata | ai-kit | webhook-mesh | ad-guard |
#           health | model-governor | drift-gate | webhook-replay | spend-guard | agent-ledger
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
SKU="${1:-}"
if [[ -z "$SKU" ]]; then
  echo "usage: $0 <sku-id>" >&2
  exit 2
fi

# shellcheck source=instpp_bootstrap.sh
source "$(dirname "$0")/instpp_bootstrap.sh"
instpp_bootstrap

WORK="${DOCKER_SKU_WORK:-/tmp/instpp_docker_sku}"
mkdir -p "$WORK"
export SKIP_LIVE="${SKIP_LIVE:-1}"
export SKIP_LIVE_LLM="${SKIP_LIVE_LLM:-1}"
export WEBHOOK_PROVIDER_SECRET="${WEBHOOK_PROVIDER_SECRET:-docker-rigorous-secret}"
export PORTFOLIO_DEMO_DIR="$WORK"

pass() { echo "[PASS] $*"; }
fail() { echo "[FAIL] $*"; exit 1; }

section() {
  echo ""
  echo "----------------------------------------------------------------"
  echo "DOCKER SKU RIGOROUS — $SKU — $*"
  echo "----------------------------------------------------------------"
}

verify_tarball() {
  local cli="$1"
  local tar="$2"
  "$PYTHON" -m "${cli}.cli" verify-bundle --tarball "$tar"
}

chain_ok() {
  local db="$1"
  "$PYTHON" -c "
from pathlib import Path
from inst_spine.ledger import AppendOnlyLedger
v = AppendOnlyLedger(Path('$db')).verify()
assert v.get('chain_ok', True), v
print('chain_ok')
"
}

section "install"
pip install -e ".[dev,instpp]" -q

case "$SKU" in
  compliance)
    section "unit tests"
    "$PYTHON" -m pytest tests/test_compliance_cli.py tests/test_compliance_serve.py -v --tb=short
    section "demo ingest → check → export → verify"
    ./scripts/demo_compliance_logger.sh \
      "$WORK/compliance.sqlite" "$WORK/compliance_bundle" "$WORK/compliance_bundle.tar"
    chain_ok "$WORK/compliance.sqlite"
    verify_tarball compliance_log "$WORK/compliance_bundle.tar"
    ;;
  proxy)
    section "unit tests"
    "$PYTHON" -m pytest tests/test_proxy_risk.py tests/test_proxy_risk_serve.py -v --tb=short
    section "demo"
    ./scripts/demo_proxy_risk.sh \
      "$WORK/proxy.sqlite" "$WORK/proxy_bundle" "$WORK/proxy_bundle.tar"
    chain_ok "$WORK/proxy.sqlite"
    verify_tarball proxy_risk "$WORK/proxy_bundle.tar"
    ;;
  altdata)
    section "unit tests"
    "$PYTHON" -m pytest tests/test_altdata_cli.py -v --tb=short
    section "demo"
    ./scripts/demo_altdata.sh "$WORK/altdata.sqlite" "$WORK/altdata_bundle.tar"
    chain_ok "$WORK/altdata.sqlite"
    verify_tarball altdata "$WORK/altdata_bundle.tar"
    ;;
  ai-kit)
    section "unit tests"
    "$PYTHON" -m pytest tests/test_ai_kit_cli.py -v --tb=short
    section "demo"
    ./scripts/demo_ai_kit.sh "$WORK/ai_kit_trace.sqlite" "$WORK/ai_kit_bundle.tar"
    chain_ok "$WORK/ai_kit_trace.sqlite"
    verify_tarball ai_kit "$WORK/ai_kit_bundle.tar"
    ;;
  webhook-mesh)
    if ! command -v curl >/dev/null 2>&1; then
      apt-get update -qq && apt-get install -y -qq curl >/dev/null
    fi
    section "unit tests"
    "$PYTHON" -m pytest tests/test_webhook_mesh.py -v --tb=short
    section "demo"
    ./scripts/demo_webhook_mesh.sh "$WORK/webhook_mesh.sqlite" "$WORK/webhook_mesh_bundle.tar"
    chain_ok "$WORK/webhook_mesh.sqlite"
    verify_tarball webhook_mesh "$WORK/webhook_mesh_bundle.tar"
    ;;
  ad-guard)
    section "unit tests"
    "$PYTHON" -m pytest tests/test_ad_guard_cli.py tests/test_ad_guard.py -v --tb=short
    section "demo"
    ./scripts/demo_ad_guard.sh "$WORK/ad_guard.sqlite" "$WORK/ad_guard_bundle.tar"
    chain_ok "$WORK/ad_guard.sqlite"
    verify_tarball ad_guard "$WORK/ad_guard_bundle.tar"
    ;;
  health)
    section "unit tests"
    "$PYTHON" -m pytest tests/test_health_telemetry.py -v --tb=short
    section "demo"
    ./scripts/demo_health_telemetry.sh "$WORK/health.sqlite" "$WORK/health_bundle.tar"
    chain_ok "$WORK/health.sqlite"
    verify_tarball health_telemetry "$WORK/health_bundle.tar"
    ;;
  model-governor)
    section "unit tests"
    "$PYTHON" -m pytest tests/test_model_governor.py -v --tb=short
    section "demo"
    ./scripts/demo_model_governor.sh "$WORK/model_governor.sqlite" "$WORK/model_governor_bundle.tar"
    chain_ok "$WORK/model_governor.sqlite"
    verify_tarball model_governor "$WORK/model_governor_bundle.tar"
    ;;
  drift-gate)
    section "unit tests"
    "$PYTHON" -m pytest tests/test_drift_gate.py -v --tb=short
    section "demo"
    ./scripts/demo_drift_gate.sh \
      "$WORK/drift_baseline.json" "$WORK/drift_gate.sqlite" "$WORK/drift_gate_bundle.tar"
    chain_ok "$WORK/drift_gate.sqlite"
    verify_tarball drift_gate "$WORK/drift_gate_bundle.tar"
    ;;
  webhook-replay)
    section "unit tests"
    "$PYTHON" -m pytest tests/test_webhook_replay.py -v --tb=short
    section "demo"
    ./scripts/demo_webhook_replay.sh \
      "$WORK/captures" "$WORK/webhook_replay.sqlite" "$WORK/webhook_replay_bundle.tar"
    chain_ok "$WORK/webhook_replay.sqlite"
    verify_tarball webhook_replay "$WORK/webhook_replay_bundle.tar"
    ;;
  spend-guard)
    section "unit tests"
    "$PYTHON" -m pytest tests/test_spend_guard.py -v --tb=short
    section "demo"
    ./scripts/demo_spend_guard.sh \
      "$WORK/spend_wallet.sqlite" "$WORK/spend_guard.sqlite" "$WORK/spend_guard_bundle.tar"
    chain_ok "$WORK/spend_guard.sqlite"
    verify_tarball spend_guard "$WORK/spend_guard_bundle.tar"
    ;;
  agent-ledger)
    section "unit tests"
    "$PYTHON" -m pytest tests/test_agent_ledger.py -v --tb=short
    section "demo"
    ./scripts/demo_agent_ledger.sh \
      "$WORK/agent_ledger.sqlite" "$WORK/agent_ledger_permits.sqlite" "$WORK/agent_ledger_bundle.tar"
    chain_ok "$WORK/agent_ledger.sqlite"
    verify_tarball agent_ledger "$WORK/agent_ledger_bundle.tar"
    ;;
  *)
    fail "unknown sku: $SKU"
    ;;
esac

section "F1-F9 institutional check"
case "$SKU" in
  compliance) CLI=compliance_log ;;
  proxy) CLI=proxy_risk ;;
  altdata) CLI=altdata ;;
  ai-kit) CLI=ai_kit ;;
  webhook-mesh) CLI=webhook_mesh ;;
  ad-guard) CLI=ad_guard ;;
  health) CLI=health_telemetry ;;
  model-governor) CLI=model_governor ;;
  drift-gate) CLI=drift_gate ;;
  webhook-replay) CLI=webhook_replay ;;
  spend-guard) CLI=spend_guard ;;
  agent-ledger) CLI=agent_ledger ;;
esac
DB="$(
  case "$SKU" in
    compliance) echo "$WORK/compliance.sqlite" ;;
    proxy) echo "$WORK/proxy.sqlite" ;;
    altdata) echo "$WORK/altdata.sqlite" ;;
    ai-kit) echo "$WORK/ai_kit_trace.sqlite" ;;
    webhook-mesh) echo "$WORK/webhook_mesh.sqlite" ;;
    ad-guard) echo "$WORK/ad_guard.sqlite" ;;
    health) echo "$WORK/health.sqlite" ;;
    model-governor) echo "$WORK/model_governor.sqlite" ;;
    drift-gate) echo "$WORK/drift_gate.sqlite" ;;
    webhook-replay) echo "$WORK/webhook_replay.sqlite" ;;
    spend-guard) echo "$WORK/spend_guard.sqlite" ;;
    agent-ledger) echo "$WORK/agent_ledger.sqlite" ;;
  esac
)"
"$PYTHON" -m "${CLI}.cli" check --database "$DB"

"$PYTHON" -c "
import json
print(json.dumps({'ok': True, 'sku': '$SKU', 'database': '$DB', 'docker_rigorous': 'passed'}))
"
pass "docker sku rigorous — $SKU"

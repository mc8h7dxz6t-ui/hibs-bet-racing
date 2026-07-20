#!/usr/bin/env bash
# Governor bundle CI — Tier 1 institutional (unit/forensic) or Tier 2 Postgres.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

GOVERNOR="${INST_GOVERNOR:-}"
TIER="${INST_TIER:-}"
PYTHON="${PYTHON:-python3}"

if [[ -z "$GOVERNOR" || -z "$TIER" ]]; then
  echo "INST_GOVERNOR and INST_TIER are required (e.g. finance, 1)" >&2
  exit 1
fi

echo "==> Governor CI: ${GOVERNOR} tier ${TIER}"

tier1_tests() {
  local gov="$1"
  case "$gov" in
    finance)
      "$PYTHON" -m pytest \
        tests/test_spend_guard.py \
        tests/test_drift_gate.py \
        tests/test_drift_golden.py \
        tests/test_drift_feature_matrix.py \
        tests/test_proxy_risk.py \
        tests/test_forensic_tiers.py::test_b1_proxy_spend_reserve_gate \
        tests/test_forensic_tiers.py::test_a4_spend_drift_survives_rebuild \
        tests/test_forensic_tiers.py::test_d_spend_reserve_p99_under_10ms \
        -v --tb=short
      ;;
    insurance)
      "$PYTHON" -m pytest \
        tests/test_model_governor.py \
        tests/test_drift_gate.py \
        tests/test_compliance_cli.py \
        tests/test_forensic_tiers.py::test_b3_model_governor_lifecycle_fsm \
        -v --tb=short
      ;;
    model)
      "$PYTHON" -m pytest \
        tests/test_model_governor.py \
        tests/test_phase3_buyer_depth.py \
        -v --tb=short
      ;;
    cyber)
      "$PYTHON" -m pytest \
        tests/test_webhook_mesh.py \
        tests/test_webhook_mesh_chaos.py \
        tests/test_ad_guard.py \
        tests/test_forensic_tiers.py::test_a3_webhook_delivery_lifecycle_on_ledger \
        -v --tb=short
      ;;
    *)
      echo "unknown governor: $gov" >&2
      exit 1
      ;;
  esac
}

tier2_tests() {
  local gov="$1"
  if [[ -z "${INST_TEST_POSTGRES_DSN:-}" ]]; then
    echo "INST_TEST_POSTGRES_DSN is required for tier 2" >&2
    exit 1
  fi
  case "$gov" in
    finance)
      "$PYTHON" -m pytest tests/test_postgres_profile.py -v --tb=short
      ;;
    insurance|model|cyber)
      "$PYTHON" -m pytest \
        tests/test_postgres_profile.py::test_postgres_compliance_ledger_append_and_verify \
        -v --tb=short
      ;;
    *)
      echo "unknown governor: $gov" >&2
      exit 1
      ;;
  esac
}

case "$TIER" in
  1) tier1_tests "$GOVERNOR" ;;
  2) tier2_tests "$GOVERNOR" ;;
  *)
    echo "unknown tier: $TIER (expected 1 or 2)" >&2
    exit 1
    ;;
esac

echo "[OK] ${GOVERNOR} tier ${TIER} passed"

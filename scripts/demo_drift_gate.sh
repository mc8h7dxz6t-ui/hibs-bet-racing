#!/usr/bin/env bash
# Drift Gate demo — baseline, shadow burn-in, enforce reject, audit bundle.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
# shellcheck source=instpp_bootstrap.sh
source "$(dirname "$0")/instpp_bootstrap.sh"
instpp_bootstrap

BASELINE="${1:-./data/demo/drift_gate_baseline.json}"
DB="${2:-./data/demo/drift_gate.sqlite}"
TAR="${3:-./data/demo/drift_gate_bundle.tar}"
mkdir -p "$(dirname "$BASELINE")" "$(dirname "$DB")" "$(dirname "$TAR")"

echo "── 1/6 Create synthetic baseline ──"
rm -f "${BASELINE%.json}.rolling.json"
"$PYTHON" -m drift_gate.cli baseline \
  --model-id credit-underwrite-v3 \
  --version v3.2.1 \
  --features '{"income":50000,"debt_ratio":0.35}' \
  --out "$BASELINE" --synthetic --samples 100

echo "── 2/6 Shadow burn-in (5 stable requests) ──"
for i in 1 2 3 4 5; do
  "$PYTHON" -m drift_gate.cli evaluate \
    --baseline "$BASELINE" \
    --features '{"income":50100,"debt_ratio":0.36}' \
    --mode shadow --database "$DB" --request-id "burn-$i" || true
done

echo "── 3/6 Shadow drifted request (still approves) ──"
"$PYTHON" -m drift_gate.cli evaluate \
  --baseline "$BASELINE" \
  --features '{"income":180000,"debt_ratio":0.92}' \
  --mode shadow --database "$DB" --request-id drift-shadow-1 || true

echo "── 4/6 Enforce drifted request (reject/kill) ──"
"$PYTHON" -m drift_gate.cli evaluate \
  --baseline "$BASELINE" \
  --features '{"income":180000,"debt_ratio":0.92}' \
  --mode enforce --database "$DB" --request-id drift-enforce-1 || true

echo "── 5/6 check ──"
"$PYTHON" -m drift_gate.cli check --database "$DB"

echo "── 6/6 export → verify-bundle ──"
"$PYTHON" -m drift_gate.cli export --database "$DB" --tarball "$TAR"
"$PYTHON" -m drift_gate.cli verify-bundle --tarball "$TAR"
echo "[PASS] Drift Gate demo → $TAR"

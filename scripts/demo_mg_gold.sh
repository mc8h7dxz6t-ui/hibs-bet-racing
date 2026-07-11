#!/usr/bin/env bash
# ModelGovernor gold demo — lifecycle FSM + drift gate at deploy + offline verify.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
# shellcheck source=instpp_bootstrap.sh
source "$(dirname "$0")/instpp_bootstrap.sh"
instpp_bootstrap

MG_DIR="${MG_GOLD_DIR:-./data/demo/mg_gold}"
DB="$MG_DIR/model_governor.sqlite"
DG_DB="$MG_DIR/drift_gate.sqlite"
TAR="$MG_DIR/model_governor_bundle.tar"
BASELINE="$MG_DIR/drift_baseline.json"
MODEL="${ROOT}/docs/demo_model_snapshot.json"
mkdir -p "$MG_DIR"

step() {
  echo ""
  echo "══════════════════════════════════════════════════════════════"
  printf "  MG GOLD %s/7 — %s\n" "$1" "$2"
  echo "══════════════════════════════════════════════════════════════"
}

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  MG GOLD — ModelGovernor lifecycle + Drift Gate deploy gate  ║"
echo "╚══════════════════════════════════════════════════════════════╝"

pip install -e ".[dev,instpp]" -q

step 1 "Register model" "FSM: register → chain entry with model snapshot"
rm -f "$DB" "$DG_DB" "$TAR" "$BASELINE"
"$PYTHON" -m model_governor.cli record \
  --action register \
  --model "$MODEL" \
  --outcome '{"status":"registered","ref":"mg-gold-1"}' \
  --database "$DB"

step 2 "Approve model" "Risk board approval on hash chain"
"$PYTHON" -m model_governor.cli record \
  --action approve \
  --model "$MODEL" \
  --outcome '{"status":"approved","approver":"risk-board","ref":"mg-gold-2"}' \
  --actor risk-board \
  --database "$DB"

step 3 "Drift baseline" "PSI/KS baseline semver for deploy gate"
cat >"$BASELINE" <<'EOF'
{
  "baseline_schema_version": "1.0",
  "model_id": "demo-mg-gold",
  "version": "1",
  "features": {
    "score": [0.42, 0.44, 0.41, 0.43, 0.45, 0.42, 0.44, 0.43, 0.41, 0.42,
              0.44, 0.43, 0.45, 0.42, 0.41, 0.43, 0.44, 0.42, 0.43, 0.44,
              0.41, 0.42, 0.43, 0.44, 0.45, 0.42, 0.43, 0.44, 0.41, 0.42]
  }
}
EOF

step 4 "Deploy with drift shadow" "Shadow burn-in — drift evaluation logged, deploy proceeds"
"$PYTHON" -m model_governor.cli record \
  --action deploy \
  --model "$MODEL" \
  --outcome '{"status":"deployed","environment":"production","ref":"mg-gold-3"}' \
  --actor ml-platform \
  --database "$DB"

step 5 "Institutional check" "F1–F9 gates on governance ledger"
"$PYTHON" -m model_governor.cli check --database "$DB"

step 6 "Export bundle" "Deterministic tarball + SHA256 sidecar"
"$PYTHON" -m model_governor.cli export --database "$DB" --tarball "$TAR"

step 7 "Offline verify" "Auditor dry-run without live database"
"$PYTHON" -m model_governor.cli verify-bundle --tarball "$TAR"

echo ""
echo "[PASS] ModelGovernor gold demo → $TAR"
echo "  Pair with: make demo-gold (Spend Guard spend plane)"

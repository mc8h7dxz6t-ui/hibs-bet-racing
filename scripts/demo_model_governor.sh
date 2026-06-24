#!/usr/bin/env bash
# ModelGovernor demo — register → approve → check → export → verify-bundle.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
# shellcheck source=instpp_bootstrap.sh
source "$(dirname "$0")/instpp_bootstrap.sh"
instpp_bootstrap
DB="${1:-./data/demo/model_governor.sqlite}"
TAR="${2:-./data/demo/model_governor_bundle.tar}"
MODEL="${ROOT}/docs/demo_model_snapshot.json"
mkdir -p "$(dirname "$DB")" "$(dirname "$TAR")"
echo "── 1/5 Register model ──"
"$PYTHON" -m model_governor.cli record \
  --action register \
  --model "$MODEL" \
  --outcome '{"status":"registered","ref":"demo-mg-001"}' \
  --database "$DB"
echo "── 2/5 Approve model ──"
"$PYTHON" -m model_governor.cli record \
  --action approve \
  --model "$MODEL" \
  --outcome '{"status":"approved","approver":"risk-board","ref":"demo-mg-002"}' \
  --actor risk-board \
  --database "$DB"
echo "── 3/5 F1–F9 check ──"
"$PYTHON" -m model_governor.cli check --database "$DB"
echo "── 4/5 Export bundle ──"
"$PYTHON" -m model_governor.cli export --database "$DB" --tarball "$TAR"
echo "── 5/5 Verify offline ──"
"$PYTHON" -m model_governor.cli verify-bundle --tarball "$TAR"
echo "[PASS] ModelGovernor demo → $TAR"

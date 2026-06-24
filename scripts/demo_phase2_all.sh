#!/usr/bin/env bash
# Phase 2 portfolio demo — drift-gate, webhook-replay, spend-guard.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
DEMO_DIR="${PHASE2_DEMO_DIR:-./data/demo/phase2}"
mkdir -p "$DEMO_DIR"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  PHASE 2 — Drift Gate · Webhook Replay · Spend Guard         ║"
echo "╚══════════════════════════════════════════════════════════════╝"

pip install -e ".[dev,instpp]" -q

chmod +x scripts/demo_drift_gate.sh scripts/demo_webhook_replay.sh scripts/demo_spend_guard.sh

./scripts/demo_drift_gate.sh \
  "$DEMO_DIR/drift_baseline.json" \
  "$DEMO_DIR/drift_gate.sqlite" \
  "$DEMO_DIR/drift_gate_bundle.tar"

./scripts/demo_webhook_replay.sh \
  "$DEMO_DIR/captures" \
  "$DEMO_DIR/webhook_replay.sqlite" \
  "$DEMO_DIR/webhook_replay_bundle.tar"

./scripts/demo_spend_guard.sh \
  "$DEMO_DIR/spend_wallet.sqlite" \
  "$DEMO_DIR/spend_guard.sqlite" \
  "$DEMO_DIR/spend_guard_bundle.tar"

echo ""
echo "[PASS] Phase 2 demo complete — 3/3 standalone SKUs"
echo "  drift-gate verify-bundle --tarball $DEMO_DIR/drift_gate_bundle.tar"
echo "  webhook-replay verify-bundle --tarball $DEMO_DIR/webhook_replay_bundle.tar"
echo "  spend-guard verify-bundle --tarball $DEMO_DIR/spend_guard_bundle.tar"

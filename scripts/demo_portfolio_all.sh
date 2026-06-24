#!/usr/bin/env bash
# Portfolio demo — all 8 institutional products in one run.
#
# Usage:
#   ./scripts/demo_portfolio_all.sh              # all 8 demos
#   ./scripts/demo_portfolio_all.sh --clean    # wipe data/demo/portfolio first
#   SKIP_LIVE=1 ./scripts/demo_portfolio_all.sh   # offline-safe (no httpbin / FX)
#   PAUSE=1 ./scripts/demo_portfolio_all.sh     # press Enter between products (recording)
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
DEMO_DIR="${PORTFOLIO_DEMO_DIR:-./data/demo/portfolio}"
SKIP_LIVE="${SKIP_LIVE:-0}"
PAUSE="${PAUSE:-0}"

export WEBHOOK_PROVIDER_SECRET="${WEBHOOK_PROVIDER_SECRET:-demo-secret}"
export SKIP_LIVE_LLM="${SKIP_LIVE_LLM:-1}"

banner() {
  echo ""
  echo "╔══════════════════════════════════════════════════════════════╗"
  printf "║  %-60s║\n" "$1"
  echo "╚══════════════════════════════════════════════════════════════╝"
  echo ""
}

product_pause() {
  local n="$1"
  local title="$2"
  local plain="$3"
  banner "PRODUCT $n/8 — $title"
  echo "  $plain"
  echo ""
  if [[ "$PAUSE" == "1" ]]; then
    read -r -p "  [PAUSE] Press Enter to run demo… "
  fi
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  echo "Usage: ./scripts/demo_portfolio_all.sh [--clean]"
  echo ""
  echo "  Runs all 8 gold-standard product demos → $DEMO_DIR/"
  echo ""
  echo "  Environment:"
  echo "    SKIP_LIVE=1          No external HTTP (proxy, alt-data FX)"
  echo "    PAUSE=1              Pause before each product (video recording)"
  echo "    PORTFOLIO_DEMO_DIR=  Output directory (default: data/demo/portfolio)"
  echo ""
  exit 0
fi

if [[ "${1:-}" == "--clean" ]]; then
  echo "==> Cleaning $DEMO_DIR"
  rm -rf "$DEMO_DIR"
fi

mkdir -p "$DEMO_DIR"

banner "PORTFOLIO — install dependencies"
pip install -e ".[dev,instpp]" -q

product_pause "1" "Compliance Logger" \
  "Plain: CCTV for business decisions — prove approve/deny with offline proof."

./scripts/demo_compliance_logger.sh \
  "$DEMO_DIR/compliance.sqlite" \
  "$DEMO_DIR/compliance_bundle" \
  "$DEMO_DIR/compliance_bundle.tar"

product_pause "2" "Proxy-Risk" \
  "Plain: Bouncer on outbound API calls — shadow, kill switch, every gate logged."

export SKIP_LIVE
./scripts/demo_proxy_risk.sh \
  "$DEMO_DIR/proxy.sqlite" \
  "$DEMO_DIR/proxy_bundle" \
  "$DEMO_DIR/proxy_bundle.tar"

product_pause "3" "Alt-Data" \
  "Plain: Smoke alarm for data feeds — coverage check before you trust the feed."

./scripts/demo_altdata.sh \
  "$DEMO_DIR/altdata.sqlite" \
  "$DEMO_DIR/altdata_bundle.tar"

product_pause "4" "AI Kit" \
  "Plain: Flight recorder for AI agents — rate limits, checkpoints, trace audit."

./scripts/demo_ai_kit.sh \
  "$DEMO_DIR/ai_kit_trace.sqlite" \
  "$DEMO_DIR/ai_kit_bundle.tar" \
  "$DEMO_DIR/ai_kit_checkpoint.sqlite"

product_pause "5" "Webhook Mesh" \
  "Plain: Never charge twice — dedupe billing webhooks, safe before you say OK."

./scripts/demo_webhook_mesh.sh \
  "$DEMO_DIR/webhook_mesh.sqlite" \
  "$DEMO_DIR/webhook_mesh_bundle.tar"

product_pause "6" "Ad Guard" \
  "Plain: Circuit breaker on Google/Meta ad API spend — kill + proof."

./scripts/demo_ad_guard.sh \
  "$DEMO_DIR/ad_guard.sqlite" \
  "$DEMO_DIR/ad_guard_bundle.tar"

product_pause "7" "Health Telemetry" \
  "Plain: Sealed device readings — tamper evidence, not a hospital EMR."

./scripts/demo_health_telemetry.sh \
  "$DEMO_DIR/health.sqlite" \
  "$DEMO_DIR/health_bundle.tar"

product_pause "8" "ModelGovernor" \
  "Plain: Signed model approvals — who deployed what, with offline proof."

./scripts/demo_model_governor.sh \
  "$DEMO_DIR/model_governor.sqlite" \
  "$DEMO_DIR/model_governor_bundle.tar"

banner "PORTFOLIO DEMO COMPLETE — 8/8"

"$PYTHON" - <<PY
import json
from pathlib import Path

demo = Path("${DEMO_DIR}")
products = [
    ("compliance_logger", demo / "compliance_bundle.tar"),
    ("proxy_risk", demo / "proxy_bundle.tar"),
    ("altdata", demo / "altdata_bundle.tar"),
    ("ai_kit", demo / "ai_kit_bundle.tar"),
    ("webhook_mesh", demo / "webhook_mesh_bundle.tar"),
    ("ad_guard", demo / "ad_guard_bundle.tar"),
    ("health_telemetry", demo / "health_bundle.tar"),
    ("model_governor", demo / "model_governor_bundle.tar"),
]
artifacts = {}
for name, tar in products:
    sidecar = tar.with_suffix(tar.suffix + ".sha256.json")
    artifacts[name] = {
        "tarball": str(tar),
        "present": tar.is_file(),
        "sidecar": str(sidecar) if sidecar.is_file() else None,
    }
passed = all(v["present"] for v in artifacts.values())
print(json.dumps({"status": "PASSED" if passed else "FAILED", "products": 8, "artifacts": artifacts}, indent=2))
PY

echo ""
echo "Verify any bundle offline, e.g.:"
echo "  compliance-log verify-bundle --tarball $DEMO_DIR/compliance_bundle.tar"
echo "  webhook-mesh verify-bundle --tarball $DEMO_DIR/webhook_mesh_bundle.tar"
echo ""
echo "Video recording: PAUSE=1 ./scripts/demo_portfolio_all.sh"
echo "  or see docs/DEMO_VIDEO_PORTFOLIO_ALL.md"
echo ""
